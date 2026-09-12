from __future__ import annotations

import shlex
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .chain import run_statement
from .dispatcher import Dispatcher
from .explain import record


class RecipeError(ValueError):
    """Raised when a recipe cannot be loaded or one of its statements fails."""


@dataclass(frozen=True, slots=True)
class RecipeStatement:
    path: Path
    line: int
    tokens: tuple[str, ...]


@dataclass(slots=True)
class RecipeSession:
    """Execute GWAY statements while preserving named context between them."""

    dispatcher: Dispatcher
    context: dict[str, object] = field(default_factory=dict)

    def run(
        self,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
    ) -> object:
        return run_statement(
            self.dispatcher,
            tokens,
            interactive=interactive,
            context=self.context,
        )


def recipe_statements(path: str | Path) -> Iterator[RecipeStatement]:
    """Yield tokenized statements from one canonical ``.rx`` recipe file."""
    recipe_path = Path(path)
    if recipe_path.suffix.lower() != ".rx":
        raise RecipeError(f"recipe file must use the .rx extension: {recipe_path}")

    try:
        source = recipe_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecipeError(f"cannot read recipe {recipe_path}: {exc}") from exc

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = tuple(shlex.split(raw_line, posix=True, comments=False))
        except ValueError as exc:
            raise RecipeError(f"{recipe_path}:{line_number}: {exc}") from exc
        if tokens:
            yield RecipeStatement(recipe_path, line_number, tokens)


def run_recipe(
    path: str | Path,
    dispatcher: Dispatcher,
    *,
    interactive: bool = False,
    on_result: Callable[[object], None] | None = None,
) -> object:
    """Execute a recipe from top to bottom in one persistent named context."""
    session = RecipeSession(dispatcher)
    result: object = None
    recipe_path = Path(path)
    record("recipe.start", "executing recipe", path=str(recipe_path))

    for statement in recipe_statements(recipe_path):
        record(
            "recipe.statement.start",
            "executing recipe statement",
            path=str(statement.path),
            line=statement.line,
            tokens=list(statement.tokens),
        )
        try:
            result = session.run(statement.tokens, interactive=interactive)
        except Exception as exc:
            record(
                "recipe.statement.failure",
                "recipe statement failed",
                path=str(statement.path),
                line=statement.line,
                error=str(exc),
            )
            raise RecipeError(f"{statement.path}:{statement.line}: {exc}") from exc
        if on_result is not None:
            on_result(result)
        record(
            "recipe.statement.result",
            "recipe statement completed",
            path=str(statement.path),
            line=statement.line,
            result=result,
        )

    record("recipe.result", "recipe completed", path=str(recipe_path), result=result)
    return result


__all__ = [
    "RecipeError",
    "RecipeSession",
    "RecipeStatement",
    "recipe_statements",
    "run_recipe",
]
