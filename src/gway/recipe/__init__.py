from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..dispatcher import Dispatcher
from ..explain import record
from ..provenance import ContinuationPoint
from ..runtime import GwayRuntime
from .context import RecipeContext, child_recipe_context
from .fitness import (
    _evaluate_fitness_once as _evaluate_fitness_once,
    _fitness_context as _fitness_context,
    evaluate_fitness,
)
from .model import RecipeError, RecipeStatement
from .parser import (
    _recipe_statement_lines,
    _recipe_statement_lines_from_source,
    recipe_statements,
)


@dataclass(slots=True)
class RecipeSession:
    """Execute multiple GWAY statements against one persistent named context."""

    dispatcher: Dispatcher
    context: MutableMapping[str, object] = field(default_factory=dict)
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


def _run_recipe_body(
    recipe_path: Path,
    session: RecipeSession,
    *,
    interactive: bool,
    prompt: Callable[[str], str] | None,
    start_statement_index: int = 1,
    initial_result: object = None,
    has_initial_result: bool = False,
    source: str | None = None,
) -> object:
    """Execute recipe statements within an already-established recipe frame."""
    assert session.runtime is not None
    result: object = initial_result if has_initial_result else None
    statement_lines = (
        _recipe_statement_lines_from_source(source, path=recipe_path)
        if source is not None
        else _recipe_statement_lines(recipe_path)
    )
    record(
        "recipe.start",
        "executing recipe",
        path=str(recipe_path),
        start_statement_index=start_statement_index,
    )
    for statement_index, statement in enumerate(
        recipe_statements(
            recipe_path,
            start_statement_index=start_statement_index,
            source=source,
        ),
        start=start_statement_index,
    ):
        next_statement_index = statement_index + 1 if statement_index < len(statement_lines) else None
        next_line = statement_lines[statement_index] if statement_index < len(statement_lines) else None
        continuation = ContinuationPoint(
            recipe_path=str(statement.path),
            statement_index=statement_index,
            line=statement.line,
            next_statement_index=next_statement_index,
            next_line=next_line,
        )
        context_provenance = getattr(session.context, "provenance", None)
        with session.runtime.frames.continuation_scope(
            continuation,
            context=session.context,
            provenance=context_provenance,
        ):
            continuation_stack = [
                point.as_dict() for point in session.runtime.frames.continuations
            ]
            record(
                "recipe.statement.start",
                "executing recipe statement",
                path=str(statement.path),
                line=statement.line,
                end_line=statement.end_line,
                tokens=list(statement.tokens),
                fitness_tokens=(
                    list(statement.fitness_tokens) if statement.fitness_tokens is not None else None
                ),
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
                if statement.fitness_tokens is not None:
                    operation_result = result
                    satisfied, fitness_result = evaluate_fitness(
                        session,
                        statement,
                        operation_result,
                        interactive=interactive,
                        prompt=prompt,
                    )
                    if not satisfied:
                        if isinstance(fitness_result, bool):
                            detail = "fitness predicate returned false"
                        else:
                            detail = (
                                "fitness predicate returned non-boolean diagnostic value "
                                f"{fitness_result!r}"
                            )
                        raise RecipeError(statement.path, detail, line=statement.line)
                    result = operation_result
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
                end_line=statement.end_line,
                result=result,
                continuation=continuation.as_dict(),
                continuation_stack=continuation_stack,
            )
    record("recipe.result", "recipe completed", path=str(recipe_path), result=result)
    return result


def _run_recipe_from(
    recipe_path: Path,
    session: RecipeSession,
    *,
    interactive: bool,
    prompt: Callable[[str], str] | None,
    start_statement_index: int,
    initial_result: object = None,
    has_initial_result: bool = False,
    source: str | None = None,
) -> object:
    """Run one recipe from a logical statement ordinal without duplicating recipe frames."""
    assert session.runtime is not None
    current = session.runtime.current_frame
    if current is not None and current.kind == "recipe" and current.recipe_path == str(recipe_path):
        return _run_recipe_body(
            recipe_path,
            session,
            interactive=interactive,
            prompt=prompt,
            start_statement_index=start_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )
    with session.runtime.frame_scope("recipe", recipe_path=str(recipe_path)):
        return _run_recipe_body(
            recipe_path,
            session,
            interactive=interactive,
            prompt=prompt,
            start_statement_index=start_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )


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
        recipe_context = RecipeContext(dict(context), provenance=context.provenance)
    else:
        recipe_context = RecipeContext(dict(context or {}))
    session = RecipeSession(dispatcher, context=recipe_context, runtime=runtime)
    return _run_recipe_from(
        Path(path),
        session,
        interactive=interactive,
        prompt=prompt,
        start_statement_index=1,
    )


__all__ = [
    "RecipeContext",
    "RecipeError",
    "RecipeSession",
    "RecipeStatement",
    "child_recipe_context",
    "recipe_statements",
    "run_recipe",
]
