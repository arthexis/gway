from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


def command_path_aliases(path: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """Return exact-normalized and reversible two-word command spellings."""
    normalized = tuple(part.replace("_", "-") for part in path)
    if not normalized:
        return (normalized,)

    words = normalized[-1].split("-")
    if len(words) != 2 or not all(words):
        return (normalized,)

    reversed_name = f"{words[1]}-{words[0]}"
    reversed_path = (*normalized[:-1], reversed_name)
    if reversed_path == normalized:
        return (normalized,)
    return normalized, reversed_path


@dataclass(frozen=True)
class Parameter:
    """Framework-neutral parameter metadata for one command argument."""

    name: str
    required: bool = False
    positional: bool = False
    annotation: object | None = None
    default: Any = None
    help: str | None = None
    options: tuple[str, ...] = field(default_factory=tuple)
    consumes_value: bool | None = None
    option_arity: int | str | None = None
    negative_options: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Command:
    """Framework-neutral description of a managed project command."""

    path: tuple[str, ...]
    summary: str | None = None
    description: str | None = None
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)
    adapter_data: object | None = None

    def __post_init__(self) -> None:
        if not self.path or any(not part for part in self.path):
            raise ValueError("command path must contain non-empty components")
