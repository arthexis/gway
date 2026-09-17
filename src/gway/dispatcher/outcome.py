from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ..command import Command
from ..explain import record
from ..outcome import CommandOutcome, resolve_outcome
from ..project import Project

_REDACTED_RESULT = "<redacted>"
_redact_command_result: ContextVar[bool] = ContextVar(
    "gway_redact_command_result",
    default=False,
)


@contextmanager
def redact_command_results() -> Iterator[None]:
    """Keep a command result available to its caller while hiding it from event logs."""
    token = _redact_command_result.set(True)
    try:
        yield
    finally:
        _redact_command_result.reset(token)


def _logged_result(value: object) -> object:
    return _REDACTED_RESULT if _redact_command_result.get() else value


def finalize_command_result(
    raw_result: object,
    *,
    project: Project,
    command: Command,
    preserve_outcome: bool = False,
) -> object:
    """Record and resolve one adapter command result."""
    if isinstance(raw_result, CommandOutcome):
        record(
            "command.outcome",
            "managed command returned explicit semantic outcome",
            project=project.name,
            command=list(command.path),
            success=raw_result.success,
            result=_logged_result(raw_result.value),
            outcome_message=raw_result.message,
        )
        display_result = raw_result.value
    else:
        display_result = raw_result

    result = raw_result if preserve_outcome else resolve_outcome(raw_result)
    record(
        "command.result",
        "adapter command completed",
        project=project.name,
        command=list(command.path),
        result=_logged_result(display_result),
    )
    return result


__all__ = ["finalize_command_result", "redact_command_results"]
