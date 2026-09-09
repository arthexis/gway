from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from sigils import Sigil

from .config import GwayPaths
from .sigils import base_context

_UNRESOLVED_SIGIL = re.compile(r"%?\[(?P<expression>.*?)\]")


def solve_values(
    values: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    paths: GwayPaths | None = None,
) -> str:
    """Resolve a CLI template using GWAY's ordinary base Sigil context.

    Unresolved Sigils are preserved in non-interactive mode. In interactive
    mode, each distinct unresolved expression is requested once and reused for
    repeated occurrences in the rendered value.
    """
    rendered = Sigil(" ".join(values)).solve(base_context(paths))
    if not interactive:
        return rendered
    if prompt is None:
        raise ValueError("interactive Sigil solving requires a prompt callback")

    answers: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        expression = match.group("expression").strip()
        if expression not in answers:
            answers[expression] = prompt(expression or "value")
        return answers[expression]

    return _UNRESOLVED_SIGIL.sub(replace, rendered)


__all__ = ["solve_values"]
