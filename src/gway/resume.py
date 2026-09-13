from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from .checkpoint import CheckpointError, ResumeCheckpoint
from .dispatcher import Dispatcher
from .explain import record
from .recipe import (
    RecipeContext,
    RecipeSession,
    _recipe_statement_lines_from_source,
    _run_recipe_from,
)
from .runtime import GwayRuntime


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


def resume_recipe(
    checkpoint: ResumeCheckpoint,
    dispatcher: Dispatcher,
    *,
    runtime: GwayRuntime | None = None,
    prompt: Callable[[str], str] | None = None,
) -> object:
    """Restore checkpoint state and continue at the recorded next recipe statement."""
    recipe_path = Path(checkpoint.recipe.path)
    payload, source = _read_recipe_snapshot(recipe_path)
    _validate_recipe_source(checkpoint, recipe_path, payload, source)

    context = RecipeContext(
        dict(checkpoint.context),
        provenance=checkpoint.context_provenance,
    )
    session = RecipeSession(dispatcher, context=context, runtime=runtime)
    assert session.runtime is not None

    point = checkpoint.continuation
    record(
        "resume.start",
        "restored recipe checkpoint",
        path=str(recipe_path),
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


__all__ = ["ResumeError", "resume_recipe"]
