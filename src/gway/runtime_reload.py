from __future__ import annotations

import os
import sys
from pathlib import Path

from .chain_context import current_chain_context, current_chain_provenance
from .checkpoint import CheckpointFlags, ResumeCheckpoint, recipe_identity
from .checkpoint_store import write_checkpoint_atomic
from .explain import enabled as explain_enabled, record


class ReloadError(RuntimeError):
    """Raised when the current runtime cannot be safely checkpointed and replaced."""


def create_reload_checkpoint(runtime, *, interactive: bool) -> ResumeCheckpoint:
    """Capture the single active recipe continuation into checkpoint version 1."""
    continuations = runtime.frames.continuations
    if len(continuations) != 1:
        if not continuations:
            raise ReloadError("reload is only supported while a recipe statement is active")
        raise ReloadError(
            "reload currently supports exactly one active recipe continuation; "
            "nested recipe resume is reserved for Chunk 7"
        )

    point = continuations[0]
    context = current_chain_context()
    provenance = current_chain_provenance()
    has_previous_result = "result" in context
    previous_result = context.get("result")
    previous_provenance = provenance.get("result")

    try:
        identity = recipe_identity(Path(point.recipe_path))
        return ResumeCheckpoint(
            recipe=identity,
            continuation=point,
            context=context,  # type: ignore[arg-type]
            context_provenance=provenance,
            has_previous_result=has_previous_result,
            previous_result=previous_result if has_previous_result else None,  # type: ignore[arg-type]
            previous_result_provenance=(
                previous_provenance if has_previous_result else None
            ),
            flags=CheckpointFlags(
                interactive=interactive,
                explain=explain_enabled(),
                output_mode=getattr(runtime, "output_mode", None),
            ),
        )
    except OSError as exc:
        raise ReloadError(f"cannot checkpoint active recipe {point.recipe_path}: {exc}") from exc


def reload_runtime(runtime, *, interactive: bool) -> None:
    """Atomically checkpoint the active recipe and replace this process with fresh GWAY."""
    checkpoint = create_reload_checkpoint(runtime, interactive=interactive)
    path = write_checkpoint_atomic(checkpoint, runtime.registry.paths.data_dir)
    argv = [sys.executable, "-m", "gway", "--resume", str(path)]
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
        # The checkpoint deliberately remains on disk so the failed handoff can
        # be inspected or resumed manually.
        raise ReloadError(f"cannot replace GWAY process; checkpoint preserved at {path}: {exc}") from exc
    raise ReloadError("process replacement unexpectedly returned")


__all__ = ["ReloadError", "create_reload_checkpoint", "reload_runtime"]
