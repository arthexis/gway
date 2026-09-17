from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RecipeStatement:
    path: Path
    line: int
    tokens: tuple[str, ...]
    end_line: int | None = None
    fitness_tokens: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class _LogicalRecipeLine:
    line: int
    end_line: int
    text: str
    continuation_parts: tuple[str, ...] = ()


class RecipeError(RuntimeError):
    def __init__(self, path: Path, message: str, *, line: int | None = None) -> None:
        self.path = path
        self.line = line
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


__all__ = ["RecipeError", "RecipeStatement"]
