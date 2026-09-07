from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Parameter:
    """Framework-neutral parameter metadata for one command argument."""

    name: str
    required: bool = False
    positional: bool = False
    annotation: object | None = None
    default: Any = None
    help: str | None = None


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
