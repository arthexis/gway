from __future__ import annotations

from dataclasses import dataclass

from .adapters import AdapterError


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Explicit semantic success/failure result returned by a GWAY command."""

    success: bool
    value: object = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise TypeError("CommandOutcome.success must be a boolean")
        if self.message is not None and not isinstance(self.message, str):
            raise TypeError("CommandOutcome.message must be a string or None")


class SemanticFailure(AdapterError):
    """Raised when a managed command explicitly reports semantic failure."""

    def __init__(self, outcome: CommandOutcome) -> None:
        self.outcome = outcome
        super().__init__(outcome.message or "GWAY command reported semantic failure")


def success(value: object = None, *, message: str | None = None) -> CommandOutcome:
    """Return an explicit successful command outcome."""
    return CommandOutcome(True, value=value, message=message)


def failure(value: object = None, *, message: str | None = None) -> CommandOutcome:
    """Return an explicit failed command outcome."""
    return CommandOutcome(False, value=value, message=message)


def resolve_outcome(value: object) -> object:
    """Unwrap explicit command outcomes and raise on semantic failure."""
    if not isinstance(value, CommandOutcome):
        return value
    if not value.success:
        raise SemanticFailure(value)
    return value.value


__all__ = [
    "CommandOutcome",
    "SemanticFailure",
    "failure",
    "resolve_outcome",
    "success",
]
