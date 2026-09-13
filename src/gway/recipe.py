from __future__ import annotations

import shlex
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .chain_context import current_chain_provenance
from .dispatcher import Dispatcher
from .explain import record
from .provenance import ContinuationPoint, ValueProvenance
from .runtime import GwayRuntime


@dataclass(frozen=True, slots=True)
class RecipeStatement:
    path: Path
    line: int
    tokens: tuple[str, ...]


class RecipeError(RuntimeError):
    def __init__(self, path: Path, message: str, *, line: int | None = None) -> None:
        self.path = path
        self.line = line
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


class RecipeContext(dict[str, object]):
    """Named recipe values with non-key provenance metadata."""

    def __init__(
        self,
        values: Mapping[str, object] | None = None,
        *,
        provenance: Mapping[str, ValueProvenance] | None = None,
    ) -> None:
        super().__init__(values or {})
        self.provenance: dict[str, ValueProvenance] = dict(provenance or {})


def _recipe_statement_lines(path: Path) -> tuple[int, ...]:
    """Return physical lines that begin logical recipe statements without parsing them."""
    return tuple(
        line_number
        for line_number, source in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if source.strip() and not source.strip().startswith("#")
    )


def recipe_statements(path: str | Path) -> Iterator[RecipeStatement]:
    """Yield tokenized GWAY statements from one canonical .rx recipe file."""
    recipe_path = Path(path)
    if recipe_path.suffix != ".rx":
        raise RecipeError(recipe_path, "recipe files must use the .rx extension")

    for line_number, source in enumerate(recipe_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = source.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            tokens = tuple(shlex.split(source, comments=False, posix=True))
        except ValueError as exc:
            raise RecipeError(recipe_path, str(exc), line=line_number) from exc
        if tokens:
            yield RecipeStatement(recipe_path, line_number, tokens)


@dataclass(slots=True)
class RecipeSession:
    """Execute multiple GWAY statements against one persistent named context."""

    dispatcher: Dispatcher
    context: dict[str, object] = field(default_factory=RecipeContext)
    runtime: GwayRuntime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, RecipeContext):
            self.context = RecipeContext(self.context)
        if self.runtime is None:
            self.runtime = GwayRuntime(self.dispatcher)

    def run(
        self,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
        prompt: Callable[[str], str] | None = None,
        recipe_path: str | Path | None = None,
        recipe_line: int | None = None,
    ) -> object:
        assert self.runtime is not None
        return self.runtime.execute(
            tokens,
            interactive=interactive,
            prompt=prompt,
            context=self.context,
            recipe_path=str(recipe_path) if recipe_path is not None else None,
            recipe_line=recipe_line,
        )


def child_recipe_context(
    parent: Mapping[str, object] | None = None,
    *,
    incoming: object = None,
    has_incoming: bool = False,
) -> RecipeContext:
    """Create an isolated child frame and explicitly publish chained input into it."""
    context = RecipeContext(parent, provenance=current_chain_provenance())
    if has_incoming:
        if isinstance(incoming, Mapping):
            context.update(incoming)
        context["result"] = incoming
    return context


def run_recipe(
    path: str | Path,
    dispatcher: Dispatcher,
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    context: MutableMapping[str, object] | None = None,
    runtime: GwayRuntime | None = None,
) -> object:
    """Execute one .rx recipe with persistent named context and fail-fast semantics."""
    if isinstance(context, RecipeContext):
        recipe_context = RecipeContext(context, provenance=context.provenance)
    else:
        recipe_context = RecipeContext(context)
    session = RecipeSession(dispatcher, context=recipe_context, runtime=runtime)
    assert session.runtime is not None
    result: object = None
    recipe_path = Path(path)
    statement_lines = _recipe_statement_lines(recipe_path)
    record("recipe.start", "executing recipe", path=str(recipe_path))
    for statement_index, statement in enumerate(recipe_statements(recipe_path), start=1):
        next_statement_index = statement_index + 1 if statement_index < len(statement_lines) else None
        next_line = statement_lines[statement_index] if statement_index < len(statement_lines) else None
        continuation = ContinuationPoint(
            recipe_path=str(statement.path),
            statement_index=statement_index,
            line=statement.line,
            next_statement_index=next_statement_index,
            next_line=next_line,
        )
        with session.runtime.frames.continuation_scope(continuation):
            continuation_stack = [
                point.as_dict() for point in session.runtime.frames.continuations
            ]
            record(
                "recipe.statement.start",
                "executing recipe statement",
                path=str(statement.path),
                line=statement.line,
                tokens=list(statement.tokens),
                continuation=continuation.as_dict(),
                continuation_stack=continuation_stack,
            )
            try:
                result = session.run(
                    statement.tokens,
                    interactive=interactive,
                    prompt=prompt,
                    recipe_path=statement.path,
                    recipe_line=statement.line,
                )
            except RecipeError:
                raise
            except SystemExit as exc:
                raise RecipeError(
                    statement.path,
                    f"statement exited with status {exc.code}",
                    line=statement.line,
                ) from exc
            except Exception as exc:
                raise RecipeError(statement.path, str(exc), line=statement.line) from exc
            record(
                "recipe.statement.result",
                "completed recipe statement",
                path=str(statement.path),
                line=statement.line,
                result=result,
                continuation=continuation.as_dict(),
                continuation_stack=continuation_stack,
            )
    record("recipe.result", "recipe completed", path=str(recipe_path), result=result)
    return result


__all__ = [
    "RecipeContext",
    "RecipeError",
    "RecipeSession",
    "RecipeStatement",
    "child_recipe_context",
    "recipe_statements",
    "run_recipe",
]
