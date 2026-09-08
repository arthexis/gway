from __future__ import annotations

from gway.dispatcher import CommandNotFound, Dispatcher
from gway.expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args


class StubDispatcher(Dispatcher):
    """Exercise expression dispatch without requiring registered projects."""

    def __init__(self, results: dict[tuple[str, ...], object]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def run(self, project_name, tokens, *, interactive=False):
        if project_name == MANAGED_EXPRESSION_PROJECT:
            return Dispatcher.run(self, project_name, tokens, interactive=interactive)

        key = (project_name, *tokens)
        self.calls.append(key)
        result = self.results.get(key, CommandNotFound("missing"))
        if isinstance(result, Exception):
            raise result
        return result


def evaluate(
    expression: str,
    results: dict[tuple[str, ...], object],
) -> tuple[object, StubDispatcher]:
    dispatcher = StubDispatcher(results)
    project, args = normalize_managed_args([expression])
    return dispatcher.run(project, args), dispatcher


def test_first_truthy_fallback_result_wins() -> None:
    result, dispatcher = evaluate(
        "primary.check|secondary.check|tertiary.check",
        {
            ("primary", "check"): "",
            ("secondary", "check"): "ready",
            ("tertiary", "check"): "later",
        },
    )
    assert result == "ready"
    assert dispatcher.calls == [("primary", "check"), ("secondary", "check")]


def test_missing_branch_falls_through_to_next_command() -> None:
    result, dispatcher = evaluate(
        "missing.check|secondary.check",
        {("secondary", "check"): "ready"},
    )
    assert result == "ready"
    assert dispatcher.calls == [("missing", "check"), ("secondary", "check")]


def test_terminal_literal_fallback_stops_evaluation() -> None:
    result, dispatcher = evaluate(
        "primary.check|:offline|secondary.check",
        {("primary", "check"): False, ("secondary", "check"): "ready"},
    )
    assert result == "offline"
    assert dispatcher.calls == [("primary", "check")]


def test_trailing_colon_returns_literal_without_dispatch() -> None:
    result, dispatcher = evaluate("health.errors:", {})
    assert result == "health.errors"
    assert dispatcher.calls == []


def test_last_resolved_falsey_value_is_returned() -> None:
    result, dispatcher = evaluate(
        "primary.check|secondary.check",
        {("primary", "check"): False, ("secondary", "check"): 0},
    )
    assert result == 0
    assert dispatcher.calls == [("primary", "check"), ("secondary", "check")]
