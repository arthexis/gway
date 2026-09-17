from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Protocol

from ..dispatcher import Dispatcher
from ..explain import record
from ..runtime import GwayRuntime
from .context import RecipeContext
from .model import RecipeStatement


class _RecipeSessionLike(Protocol):
    dispatcher: Dispatcher
    context: MutableMapping[str, object]
    runtime: GwayRuntime | None


def _fitness_context(session: _RecipeSessionLike) -> RecipeContext:
    """Copy current semantic context so fitness evaluation cannot overwrite recipe state."""
    provenance = getattr(session.context, "provenance", None)
    return RecipeContext(dict(session.context), provenance=provenance)


def evaluate_fitness(
    session: _RecipeSessionLike,
    statement: RecipeStatement,
    operation_result: object,
    *,
    interactive: bool,
    prompt: Callable[[str], str] | None,
) -> tuple[bool, object]:
    """Evaluate fitness once using normal GWAY result-transfer and context resolution."""
    from ..chain import run_statement

    assert statement.fitness_tokens is not None
    assert session.runtime is not None
    fitness_context = _fitness_context(session)
    fitness_result = run_statement(
        session.dispatcher,
        statement.fitness_tokens,
        interactive=interactive,
        prompt=prompt,
        context=fitness_context,
        provenance=fitness_context.provenance,
        runtime=session.runtime,
        initial_result=operation_result,
        has_initial_result=True,
    )
    satisfied = isinstance(fitness_result, bool) and fitness_result
    record(
        "recipe.fitness.result",
        "evaluated recipe fitness predicate",
        path=str(statement.path),
        line=statement.line,
        end_line=statement.end_line,
        fitness_tokens=list(statement.fitness_tokens),
        satisfied=satisfied,
        result=fitness_result,
        boolean=isinstance(fitness_result, bool),
    )
    return satisfied, fitness_result


__all__ = ["evaluate_fitness"]
