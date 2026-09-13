from __future__ import annotations

from collections.abc import Callable, Sequence

from .chain_context import current_chain_context
from .config import GwayPaths
from .explain import record
from .solve import solve_values


def run_result(
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    paths: GwayPaths | None = None,
) -> object:
    """Return the latest captured result, or resolve an explicit result expression."""
    context = current_chain_context()
    if not tokens:
        value = context.get("result")
        record(
            "context.result",
            "returned latest captured execution result",
            result=value,
        )
        return value

    value = solve_values(
        tokens,
        interactive=interactive,
        prompt=prompt,
        paths=paths,
    )
    record(
        "context.result",
        "resolved explicit expression against execution context",
        expression=list(tokens),
        result=value,
    )
    return value


__all__ = ["run_result"]
