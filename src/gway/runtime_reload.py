from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .chain_context import current_chain_context, current_chain_provenance
from .checkpoint import CheckpointFlags, ResumeCheckpoint, recipe_identity
from .checkpoint.chain import (
    ChainContinuationCheckpoint,
    PendingChainCheckpoint,
    PendingStageCheckpoint,
)
from .checkpoint.stack import ContinuationFrameCheckpoint, ContinuationStackCheckpoint
from .checkpoint.store import write_checkpoint_atomic
from .explain import enabled as explain_enabled, record
from .recipe import recipe_statements
from .stage import StageKind, parse_stages

_ORIGINAL_ARGV_ENV = "GWAY_RESUME_ORIGINAL_ARGV"


class ReloadError(RuntimeError):
    """Raised when the current runtime cannot be safely checkpointed and replaced."""


def _checkpoint_flags(runtime, *, interactive: bool) -> CheckpointFlags:
    return CheckpointFlags(
        interactive=interactive,
        explain=explain_enabled(),
        output_mode=getattr(runtime, "output_mode", None),
    )


def capture_pending_chains(runtime) -> tuple[PendingChainCheckpoint, ...]:
    """Convert live evaluator chain state into portable checkpoint state."""
    pending: list[PendingChainCheckpoint] = []
    for state in runtime.frames.active_chains:
        stages = parse_stages(state.statement_tokens)
        remaining = stages[state.active_stage_index :]
        if not remaining:
            continue
        pending.append(
            PendingChainCheckpoint(
                frame_id=state.frame_id,
                recipe_path=state.recipe_path,
                recipe_line=state.recipe_line,
                statement_tokens=state.statement_tokens,
                active_stage_index=state.active_stage_index,
                remaining_stages=tuple(
                    PendingStageCheckpoint.from_stage(stage) for stage in remaining
                ),
                has_previous_result=state.has_previous_result,
                previous_result=(state.previous_result if state.has_previous_result else None),  # type: ignore[arg-type]
                previous_result_provenance=(
                    state.previous_result_provenance if state.has_previous_result else None
                ),
            )
        )
    return tuple(pending)


def _validate_nested_parent_statement(parent, child) -> None:
    try:
        statement = next(
            recipe_statements(
                parent.point.recipe_path,
                start_statement_index=parent.point.statement_index,
            )
        )
        stages = parse_stages(statement.tokens)
    except Exception as exc:
        raise ReloadError(
            f"cannot validate nested recipe continuation {parent.point.recipe_path}: {exc}"
        ) from exc

    recipe_stages = [
        stage
        for stage in stages
        if stage.kind is not StageKind.SOLVE
        and stage.tokens
        and stage.tokens[0] == "recipe"
        and len(stage.tokens) == 2
        and Path(stage.tokens[1]).resolve() == Path(child.point.recipe_path).resolve()
    ]
    if len(recipe_stages) != 1:
        raise ReloadError("nested continuation child does not match exactly one parent recipe stage")


def _create_single_checkpoint(runtime, *, interactive: bool) -> ResumeCheckpoint:
    point = runtime.frames.continuations[0]
    context = current_chain_context()
    provenance = current_chain_provenance()
    has_previous_result = "result" in context
    previous_result = context.get("result")
    previous_provenance = provenance.get("result")
    return ResumeCheckpoint(
        recipe=recipe_identity(Path(point.recipe_path)),
        continuation=point,
        context=context,  # type: ignore[arg-type]
        context_provenance=provenance,
        has_previous_result=has_previous_result,
        previous_result=previous_result if has_previous_result else None,  # type: ignore[arg-type]
        previous_result_provenance=previous_provenance if has_previous_result else None,
        flags=_checkpoint_flags(runtime, interactive=interactive),
    )


def _create_stack_checkpoint(runtime, *, interactive: bool) -> ContinuationStackCheckpoint:
    active = runtime.frames.active_continuations
    continuations = runtime.frames.continuations
    if len(active) != len(continuations):
        raise ReloadError("nested recipe continuation state is incomplete")
    for parent, child in zip(active, active[1:]):
        _validate_nested_parent_statement(parent, child)

    frames: list[ContinuationFrameCheckpoint] = []
    parent_frame_id: str | None = None
    for state in active:
        context = dict(state.context)
        provenance = dict(state.provenance)
        has_previous_result = "result" in context
        previous_result = context.get("result")
        previous_provenance = provenance.get("result")
        frames.append(
            ContinuationFrameCheckpoint(
                frame_id=state.frame_id,
                parent_frame_id=parent_frame_id,
                recipe=recipe_identity(Path(state.point.recipe_path)),
                continuation=state.point,
                context=context,  # type: ignore[arg-type]
                context_provenance=provenance,
                has_previous_result=has_previous_result,
                previous_result=previous_result if has_previous_result else None,  # type: ignore[arg-type]
                previous_result_provenance=previous_provenance if has_previous_result else None,
            )
        )
        parent_frame_id = state.frame_id
    return ContinuationStackCheckpoint(
        frames=tuple(frames), flags=_checkpoint_flags(runtime, interactive=interactive)
    )


def create_reload_checkpoint(
    runtime,
    *,
    interactive: bool,
) -> ResumeCheckpoint | ContinuationStackCheckpoint | ChainContinuationCheckpoint:
    """Capture active recipe and pending-chain continuations for process replacement."""
    continuations = runtime.frames.continuations
    if not continuations:
        raise ReloadError("reload is only supported while a recipe statement is active")

    try:
        pending = capture_pending_chains(runtime)
        if pending:
            stack = _create_stack_checkpoint(runtime, interactive=interactive)
            return ChainContinuationCheckpoint(
                frames=stack.frames,
                pending_chains=pending,
                flags=stack.flags,
            )
        if len(continuations) == 1:
            return _create_single_checkpoint(runtime, interactive=interactive)
        return _create_stack_checkpoint(runtime, interactive=interactive)
    except OSError as exc:
        point = continuations[-1]
        raise ReloadError(f"cannot checkpoint active recipe {point.recipe_path}: {exc}") from exc


def reload_runtime(runtime, *, interactive: bool) -> None:
    """Atomically checkpoint active recipes and replace this process with fresh GWAY."""
    checkpoint = create_reload_checkpoint(runtime, interactive=interactive)
    path = write_checkpoint_atomic(checkpoint, runtime.registry.paths.data_dir)
    argv = [sys.executable, "-m", "gway", "--resume", str(path)]
    os.environ[_ORIGINAL_ARGV_ENV] = json.dumps(sys.argv[1:], ensure_ascii=False)
    record(
        "reload.exec",
        "replacing process from persisted recipe checkpoint",
        checkpoint=str(path),
        executable=sys.executable,
        argv=argv[1:],
    )
    try:
        os.execv(sys.executable, argv)
    except OSError as exc:
        raise ReloadError(f"cannot replace GWAY process; checkpoint preserved at {path}: {exc}") from exc
    raise ReloadError("process replacement unexpectedly returned")


__all__ = [
    "ReloadError",
    "capture_pending_chains",
    "create_reload_checkpoint",
    "reload_runtime",
]
