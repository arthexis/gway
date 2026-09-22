"""Execution lifecycle for recipe invocations."""

from pathlib import Path

from ..tokens import statements
from .frame import RecipeFrame
from .loading import load_recipe
from .path import companion_path
from .require import collect_recipe_requirements, prepare_required_companion


_NO_PIPELINE = object()


def ingest_companion(runtime, recipe_filename):
    """Ingest a recipe's sibling Python companion once per Gateway."""
    companion = companion_path(recipe_filename)
    if companion is None:
        return []

    ingested = getattr(runtime, "_recipe_companions", None)
    if ingested is None:
        ingested = set()
        runtime._recipe_companions = ingested

    if companion in ingested:
        return []

    wrapped = runtime.ingest_path(companion)
    ingested.add(companion)
    return wrapped


def execute_recipe(
    runtime,
    recipe_filename,
    *,
    context=None,
    section=None,
    pipeline=_NO_PIPELINE,
):
    """Execute one recipe in the caller's runtime and return its internal results."""
    path = Path(recipe_filename).expanduser().resolve()
    runtime.launchables.recipe(
        path,
        metadata={"recipe": str(path)},
    )
    stack = getattr(runtime, "_recipe_stack", None)
    if stack is None:
        stack = []
        runtime._recipe_stack = stack

    if path in stack:
        cycle = " -> ".join(str(item) for item in (*stack, path))
        raise RuntimeError(f"Recipe cycle: {cycle}")

    stack.append(path)
    frames = getattr(runtime, "_recipe_frames", None)
    if frames is None:
        frames = []
        runtime._recipe_frames = frames
    frame = None
    try:
        if context:
            runtime.context.update(context)

        commands, _ = load_recipe(path, section=section)
        statement_list = []
        for command in commands:
            statement_list.extend(statements(command.get("tokens", ())))

        if not statement_list:
            return [], None

        from .environment import recipe_environment

        preflight_requirements = collect_recipe_requirements(statement_list)
        frame = RecipeFrame(
            path=path,
            statements=[list(statement) for statement in statement_list],
            invocation_context=dict(context or {}),
            section=section,
            environment=recipe_environment(runtime, path),
            preflight_requirements=preflight_requirements,
        )
        frames.append(frame)

        if preflight_requirements:
            prepare_required_companion(runtime, frame)
        else:
            ingest_companion(runtime, path)

        from ..dispatch import dispatch_program

        if pipeline is _NO_PIPELINE:
            return dispatch_program(runtime, statement_list, recipe_frame=frame)
        return dispatch_program(
            runtime,
            statement_list,
            pipeline=pipeline,
            recipe_frame=frame,
        )
    finally:
        if frame is not None and frame.companion_worker is not None:
            from .companion import unregister_worker_operations

            unregister_worker_operations(runtime, frame.companion_worker)
            frame.companion_worker.close()
        if frame is not None and frames and frames[-1] is frame:
            frames.pop()
        stack.pop()
