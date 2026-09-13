from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path

from .checkpoint import CheckpointError, ResumeCheckpoint
from .checkpoint_chain import ChainContinuationCheckpoint, PendingChainCheckpoint
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
    pass


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
    if hashlib.sha256(payload).hexdigest() != checkpoint.recipe.sha256:
        raise ResumeError(f"recipe changed since checkpoint was created: {path}")
    lines = _recipe_statement_lines_from_source(source)
    point = checkpoint.continuation
    if point.statement_index > len(lines) or lines[point.statement_index - 1] != point.line:
        raise ResumeError("checkpoint current statement does not match recipe source")
    if point.next_statement_index is None:
        if point.statement_index != len(lines):
            raise ResumeError("checkpoint omits a next statement before recipe completion")
        return lines
    if point.next_statement_index != point.statement_index + 1:
        raise ResumeError("checkpoint next statement must immediately follow current statement")
    if point.next_statement_index > len(lines) or lines[point.next_statement_index - 1] != point.next_line:
        raise ResumeError("checkpoint next statement does not match recipe source")
    return lines


def _resume_v1_checkpoint(
    checkpoint: ResumeCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None,
    prompt: Callable[[str], str] | None,
) -> object:
    recipe_path = Path(checkpoint.recipe.path)
    payload, source = _read_recipe_snapshot(recipe_path)
    _validate_recipe_source(checkpoint, recipe_path, payload, source)
    context = RecipeContext(dict(checkpoint.context), provenance=checkpoint.context_provenance)
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
            "'recipe PATH' statement; pending chain-stage restoration requires a v3 checkpoint"
        )
    if Path(stages[0].tokens[1]).resolve() != Path(child.recipe.path).resolve():
        raise ResumeError("nested checkpoint child does not match the parent recipe invocation")


def _publish_child_result(
    context: RecipeContext,
    result: object,
    *,
    provenance: ValueProvenance,
) -> None:
    if isinstance(result, Mapping):
        context.update(result)
        for key in result:
            context.provenance[str(key)] = provenance
    context["result"] = result
    context.provenance["result"] = provenance


def _snapshots(stack: ContinuationStackCheckpoint) -> tuple[tuple[Path, str], ...]:
    items = []
    for frame in stack.frames:
        path = Path(frame.recipe.path)
        payload, source = _read_recipe_snapshot(path)
        _validate_recipe_source(
            frame.as_resume_checkpoint(flags=stack.flags),
            path,
            payload,
            source,
        )
        items.append((path, source))
    return tuple(items)


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
            provenance = ValueProvenance(
                frame_id=child.frame_id,
                frame_kind="recipe",
                operation="recipe",
                recipe_path=child.recipe.path,
            )
            _publish_child_result(context, child_result, provenance=provenance)
            initial_result, has_initial_result = child_result, True
        else:
            initial_result, has_initial_result = frame.previous_result, frame.has_previous_result
        if point.next_statement_index is None:
            return initial_result if has_initial_result else None
        return _run_recipe_from(
            recipe_path,
            session,
            interactive=stack.flags.interactive,
            prompt=prompt,
            start_statement_index=point.next_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )


def _resume_stack_checkpoint(
    stack: ContinuationStackCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None,
    prompt: Callable[[str], str] | None,
) -> object:
    active_runtime = runtime or GwayRuntime(dispatcher)
    snapshots = _snapshots(stack)
    for index in range(len(stack.frames) - 1):
        _validate_parent_child_invocation(
            stack.frames[index],
            stack.frames[index + 1],
            source=snapshots[index][1],
        )
    result = _resume_frame(stack, snapshots, 0, dispatcher, active_runtime, prompt)
    record("resume.result", "resumed recipe stack completed", result=result)
    return result


def _pending_by_frame(
    checkpoint: ChainContinuationCheckpoint,
) -> dict[str, PendingChainCheckpoint]:
    return {chain.frame_id: chain for chain in checkpoint.pending_chains}


def _validate_v3_parent_child(
    parent: ContinuationFrameCheckpoint,
    child: ContinuationFrameCheckpoint,
    pending: PendingChainCheckpoint | None,
) -> None:
    if pending is None:
        raise ResumeError("v3 nested parent frame is missing pending chain state")
    stages = parse_stages(pending.statement_tokens)
    active = pending.active_stage_index - 1
    stage = stages[active]
    if (
        stage.kind is StageKind.SOLVE
        or not stage.tokens
        or stage.tokens[0] != "recipe"
        or len(stage.tokens) != 2
    ):
        raise ResumeError("v3 parent active stage is not the suspended child recipe invocation")
    if Path(stage.tokens[1]).resolve() != Path(child.recipe.path).resolve():
        raise ResumeError("v3 child does not match its parent active recipe stage")


def _resume_pending_statement(
    runtime: GwayRuntime,
    dispatcher: Dispatcher,
    context: RecipeContext,
    pending: PendingChainCheckpoint,
    *,
    initial_result: object,
    has_initial_result: bool,
    initial_provenance: ValueProvenance | None,
    interactive: bool,
    prompt: Callable[[str], str] | None,
) -> object:
    from .chain import run_statement

    with runtime.frame_scope(
        "statement",
        tokens=pending.statement_tokens,
        recipe_path=pending.recipe_path,
        recipe_line=pending.recipe_line,
    ):
        return run_statement(
            dispatcher,
            pending.statement_tokens,
            interactive=interactive,
            prompt=prompt,
            context=context,
            provenance=context.provenance,
            runtime=runtime,
            start_stage_index=pending.active_stage_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            initial_result_provenance=initial_provenance,
        )


def _resume_v3_frame(
    checkpoint: ChainContinuationCheckpoint,
    snapshots: tuple[tuple[Path, str], ...],
    pending_by_frame: dict[str, PendingChainCheckpoint],
    index: int,
    dispatcher: Dispatcher,
    runtime: GwayRuntime,
    prompt: Callable[[str], str] | None,
) -> object:
    frame = checkpoint.frames[index]
    recipe_path, source = snapshots[index]
    point = frame.continuation
    context = RecipeContext(dict(frame.context), provenance=frame.context_provenance)
    session = RecipeSession(dispatcher, context=context, runtime=runtime)
    pending = pending_by_frame.get(frame.frame_id)
    with runtime.frames.restored_scope(
        frame.frame_id,
        "recipe",
        expected_parent_id=frame.parent_frame_id,
        recipe_path=str(recipe_path),
    ):
        if index + 1 < len(checkpoint.frames):
            with runtime.frames.continuation_scope(
                point,
                context=context,
                provenance=context.provenance,
            ):
                child_result = _resume_v3_frame(
                    checkpoint,
                    snapshots,
                    pending_by_frame,
                    index + 1,
                    dispatcher,
                    runtime,
                    prompt,
                )
            child = checkpoint.frames[index + 1]
            result_provenance = ValueProvenance(
                frame_id=child.frame_id,
                frame_kind="recipe",
                operation="recipe",
                recipe_path=child.recipe.path,
            )
            _publish_child_result(context, child_result, provenance=result_provenance)
            current_result, has_result = child_result, True
        else:
            current_result = pending.previous_result if pending is not None else frame.previous_result
            has_result = (
                pending.has_previous_result if pending is not None else frame.has_previous_result
            )
            result_provenance = (
                pending.previous_result_provenance
                if pending is not None
                else frame.previous_result_provenance
            )

        if pending is not None and pending.remaining_stages:
            current_result = _resume_pending_statement(
                runtime,
                dispatcher,
                context,
                pending,
                initial_result=current_result,
                has_initial_result=has_result,
                initial_provenance=result_provenance,
                interactive=checkpoint.flags.interactive,
                prompt=prompt,
            )
            has_result = True

        if point.next_statement_index is None:
            return current_result if has_result else None
        return _run_recipe_from(
            recipe_path,
            session,
            interactive=checkpoint.flags.interactive,
            prompt=prompt,
            start_statement_index=point.next_statement_index,
            initial_result=current_result,
            has_initial_result=has_result,
            source=source,
        )


def _resume_v3_checkpoint(
    checkpoint: ChainContinuationCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None,
    prompt: Callable[[str], str] | None,
) -> object:
    active_runtime = runtime or GwayRuntime(dispatcher)
    snapshots = _snapshots(checkpoint.stack)
    pending = _pending_by_frame(checkpoint)
    for index in range(len(checkpoint.frames) - 1):
        _validate_v3_parent_child(
            checkpoint.frames[index],
            checkpoint.frames[index + 1],
            pending.get(checkpoint.frames[index].frame_id),
        )
    result = _resume_v3_frame(
        checkpoint,
        snapshots,
        pending,
        0,
        dispatcher,
        active_runtime,
        prompt,
    )
    record("resume.result", "resumed pending chain checkpoint", result=result)
    return result


def resume_recipe(
    checkpoint: ResumeCheckpoint | ContinuationStackCheckpoint | ChainContinuationCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None = None,
    prompt: Callable[[str], str] | None = None,
) -> object:
    if isinstance(checkpoint, ResumeCheckpoint):
        return _resume_v1_checkpoint(checkpoint, dispatcher, runtime=runtime, prompt=prompt)
    if isinstance(checkpoint, ChainContinuationCheckpoint):
        return _resume_v3_checkpoint(checkpoint, dispatcher, runtime=runtime, prompt=prompt)
    return _resume_stack_checkpoint(checkpoint, dispatcher, runtime=runtime, prompt=prompt)


__all__ = ["ResumeError", "resume_recipe"]
