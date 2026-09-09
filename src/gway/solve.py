from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from sigils import Sigil

from .config import GwayPaths
from .sigils import base_context
from .stage import replace_bracket_escapes

_UNRESOLVED_SIGIL = re.compile(r"%?\[(?P<expression>.*?)\]")
_EXACT_SIGIL = re.compile(r"%?\[(?P<expression>.*?)\]\Z")
_LEFT_ESCAPE = "\x00gway-left-bracket\x00"
_RIGHT_ESCAPE = "\x00gway-right-bracket\x00"


def _protect_escapes(values: Sequence[str]) -> str:
    """Join a template while shielding lexical bracket escapes from Sigils."""
    return " ".join(
        replace_bracket_escapes(
            value,
            left=_LEFT_ESCAPE,
            right=_RIGHT_ESCAPE,
        )
        for value in values
    )


def _restore_escapes(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.replace(_LEFT_ESCAPE, "[").replace(_RIGHT_ESCAPE, "]")


def _solve_template(template: str, context: dict[str, object]) -> object:
    """Resolve one template, retaining the native value of an exact Sigil."""
    sigil = Sigil(template)
    exact = _EXACT_SIGIL.fullmatch(template)
    if exact is not None:
        expression = exact.group("expression")
        solved = sigil.results(context)
        if expression in solved:
            return solved[expression]
    return sigil.solve(context)


def solve_values(
    values: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    paths: GwayPaths | None = None,
) -> object:
    """Resolve a greedy CLI template using GWAY's ordinary base Sigil context.

    An exact single Sigil preserves its resolved native type. Templates with
    surrounding text render to strings. Unresolved Sigils are preserved in
    non-interactive mode. In interactive mode, each distinct unresolved
    expression is requested once and reused for repeated occurrences.
    """
    template = _protect_escapes(values)
    rendered = _restore_escapes(_solve_template(template, base_context(paths)))

    if not interactive or not isinstance(rendered, str):
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
