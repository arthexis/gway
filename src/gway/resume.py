from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path

from .checkpoint import CheckpointError, ResumeCheckpoint
from .checkpoint_stack import ContinuationFrameCheckpoint, ContinuationStackCheckpoint
from .dispatcher import Dispatcher
from .explain import record
from .provenance import ValueProvenance
from .recipe import (
    RecipeContext,
    RecipeSession,
    _recipe_statement_lines_from_source,
    _run_recipe_from,
    recipe_statements,
)
from .runtime import GwayRuntime
from .stage import StageKind, parse_stages


class ResumeError(CheckpointError):
    """Raised when validated checkpoint state cannot be resumed against its recipe."""


def _read_recipe_snapshot(path: Path) -> tuple[bytes, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ResumeError(f"cannot read checkpoint recipe {path}: {exc}") from exc
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResumeError(f"checkpoint recipe is not valid UTF-8: {path}") from exc
    return payload, source


def _validate_recipe_source(
    checkpoint: ResumeCheckpoint,
    path: Path,
    payload: bytes,
    source: str,
) -> tuple[int, ...]:
    """Verify one immutable recipe snapshot and its continuation pointer."""
    digest = hashlib.sha256(payload).hexdigest()
    if digest != checkpoint.recipe.sha256:
        raise ResumeError(f"recipe changed since checkpoint was created: {path}")

    lines = _recipe_statement_lines_from_source(source)
    point = checkpoint.continuation
    if point.statement_index > len(lines) or lines[point.statement_index - 1] != point.line:
        raise ResumeError("checkpoint current statement does not match recipe source")

    next_index = point.next_statement_index
    next_line = point.next_line
    if next_index is None:
        if point.statement_index != len(lines):
            raise ResumeError("checkpoint omits a next statement before recipe completion")
        return lines

    if next_index != point.statement_index + 1:
        raise ResumeError("checkpoint next statement must immediately follow current statement")
    if next_index > len(lines) or lines[next_index - 1] != next_line:
        raise ResumeError("checkpoint next statement does not match recipe source")
    return lines


def _resume_v1_checkpoint(
    checkpoint: ResumeCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None,
    prompt: Callable[[str], str] | None,
) -> object:
    """Preserve the Chunk 6 single-recipe resume path unchanged."""
    recipe_path = Path(checkpoint.recipe.path)
    payload, source = _read_recipe_snapshot(recipe_path)
    _validate_recipe_source(checkpoint, recipe_path, payload, source)

    context = RecipeContext(
        dict(checkpoint.context),
        provenance=checkpoint.context_provenance,
    )
    session = RecipeSession(dispatcher, context=context, runtime=runtime)
    point = checkpoint.continuation
    record(
        "resume.start",
        "restored recipe checkpoint",
        path=str(recipe_path),
        stack_depth=1,
        current_statement_index=point.statement_index,
        next_statement_index=point.next_statement_index,
        previous_result=checkpoint.previous_result if checkpoint.has_previous_result else None,
        previous_result_provenance=(
            checkpoint.previous_result_provenance.as_dict()
            if checkpoint.previous_result_provenance is not None
            else None
        ),
        interactive=checkpoint.flags.interactive,
        explain=checkpoint.flags.explain,
        output_mode=checkpoint.flags.output_mode,
    )

    if point.next_statement_index is None:
        result = checkpoint.previous_result if checkpoint.has_previous_result else None
        record("resume.result", "checkpoint already points at recipe completion", result=result)
        return result

    result = _run_recipe_from(
        recipe_path,
        session,
        interactive=checkpoint.flags.interactive,
        prompt=prompt,
        start_statement_index=point.next_statement_index,
        initial_result=checkpoint.previous_result,
        has_initial_result=checkpoint.has_previous_result,
        source=source,
    )
    record("resume.result", "resumed recipe completed", result=result)
    return result


def _validate_parent_child_invocation(
    parent: ContinuationFrameCheckpoint,
    child: ContinuationFrameCheckpoint,
    *,
    source: str,
) -> None:
    """Ensure nested unwind does not discard chain stages reserved for Chunk 7.3."""
    try:
        statement = next(
            recipe_statements(
                parent.recipe.path,
                start_statement_index=parent.continuation.statement_index,
                source=source,
            )
        )
        stages = parse_stages(statement.tokens)
    except (StopIteration, ValueError) as exc:
        raise ResumeError("cannot resolve nested parent recipe statement") from exc

    if (
        len(stages) != 1
        or stages[0].kind is StageKind.SOLVE
        or not stages[0].tokens
        or stages[0].tokens[0] != "recipe"
        or len(stages[0].tokens) != 2
    ):
        raise ResumeError(
            "nested resume requires each parent invocation to be a single-stage "
            "'recipe PATH' statement; pending chain-stage restoration is reserved "
            "for Chunk 7.3"
        )

    expected_child = Path(stages[0].tokens[1]).resolve()
    actual_child = Path(child.recipe.path).resolve()
    if expected_child != actual_child:
        raise ResumeError(
            "nested checkpoint child does not match the parent recipe invocation"
        )


def _publish_child_result(
    context: RecipeContext,
    result: object,
    *,
    provenance: ValueProvenance,
) -> None:
    """Apply the publication that the suspended parent recipe stage would have performed."""
    if isinstance(result, Mapping):
        context.update(result)
        for key in result:
            context.provenance[str(key)] = provenance
    context["result"] = result
    context.provenance["result"] = provenance


def _resume_frame(
    stack: ContinuationStackCheckpoint,
    snapshots: tuple[tuple[Path, str], ...],
    index: int,
    dispatcher: Dispatcher,
    runtime: GwayRuntime,
    prompt: Callable[[str], str] | None,
) -> object:
    frame = stack.frames[index]
    recipe_path, source = snapshots[index]
    context = RecipeContext(dict(frame.context), provenance=frame.context_provenance)
    session = RecipeSession(dispatcher, context=context, runtime=runtime)
    point = frame.continuation

    with runtime.frames.restored_scope(
        frame.frame_id,
        "recipe",
        expected_parent_id=frame.parent_frame_id,
        recipe_path=str(recipe_path),
    ):
        record(
            "resume.frame.restore",
            "restored recipe continuation frame",
            frame_id=frame.frame_id,
            parent_frame_id=frame.parent_frame_id,
            path=str(recipe_path),
            current_statement_index=point.statement_index,
            next_statement_index=point.next_statement_index,
        )

        if index + 1 < len(stack.frames):
            with runtime.frames.continuation_scope(
                point,
                context=context,
                provenance=context.provenance,
            ):
                child_result = _resume_frame(
                    stack,
                    snapshots,
                    index + 1,
                    dispatcher,
                    runtime,
                    prompt,
                )

            child = stack.frames[index + 1]
            child_provenance = ValueProvenance(
                frame_id=child.frame_id,
                frame_kind="recipe",
                operation="recipe",
                recipe_path=child.recipe.path,
            )
            _publish_child_result(
                context,
                child_result,
                provenance=child_provenance,
            )
            initial_result = child_result
            has_initial_result = True
        else:
            initial_result = frame.previous_result
            has_initial_result = frame.has_previous_result

        if point.next_statement_index is None:
            result = initial_result if has_initial_result else None
            record(
                "resume.frame.result",
                "restored recipe frame completed at checkpoint boundary",
                frame_id=frame.frame_id,
                result=result,
            )
            return result

        result = _run_recipe_from(
            recipe_path,
            session,
            interactive=stack.flags.interactive,
            prompt=prompt,
            start_statement_index=point.next_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )
        record(
            "resume.frame.result",
            "resumed recipe frame completed",
            frame_id=frame.frame_id,
            result=result,
        )
        return result


def _resume_stack_checkpoint(
    stack: ContinuationStackCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None,
    prompt: Callable[[str], str] | None,
) -> object:
    active_runtime = runtime or GwayRuntime(dispatcher)
    snapshots_list: list[tuple[Path, str]] = []
    for frame in stack.frames:
        recipe_path = Path(frame.recipe.path)
        payload, source = _read_recipe_snapshot(recipe_path)
        _validate_recipe_source(
            frame.as_resume_checkpoint(flags=stack.flags),
            recipe_path,
            payload,
            source,
        )
        snapshots_list.append((recipe_path, source))

    snapshots = tuple(snapshots_list)
    for index in range(len(stack.frames) - 1):
        _validate_parent_child_invocation(
            stack.frames[index],
            stack.frames[index + 1],
            source=snapshots[index][1],
        )

    leaf = stack.leaf
    record(
        "resume.start",
        "restored recipe checkpoint",
        path=leaf.recipe.path,
        stack_depth=len(stack.frames),
        current_statement_index=leaf.continuation.statement_index,
        next_statement_index=leaf.continuation.next_statement_index,
        previous_result=leaf.previous_result if leaf.has_previous_result else None,
        previous_result_provenance=(
            leaf.previous_result_provenance.as_dict()
            if leaf.previous_result_provenance is not None
            else None
        ),
        interactive=stack.flags.interactive,
        explain=stack.flags.explain,
        output_mode=stack.flags.output_mode,
    )

    result = _resume_frame(
        stack,
        snapshots,
        0,
        dispatcher,
        active_runtime,
        prompt,
    )
    record("resume.result", "resumed recipe stack completed", result=result)
    return result


def resume_recipe(
    checkpoint: ResumeCheckpoint | ContinuationStackCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None = None,
    prompt: Callable[[str], str] | None = None,
) -> object:
    """Restore one v1 checkpoint or a nested v2 continuation stack."""
    if isinstance(checkpoint, ResumeCheckpoint):
        return _resume_v1_checkpoint(
            checkpoint,
            dispatcher,
            runtime=runtime,
            prompt=prompt,
        )
    return _resume_stack_checkpoint(
        checkpoint,
        dispatcher,
        runtime=runtime,
        prompt=prompt,
    )


__all__ = ["ResumeError", "resume_recipe"]
