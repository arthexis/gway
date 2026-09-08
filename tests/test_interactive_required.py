from __future__ import annotations

from gway.cli import _extract_global_flags
from gway.command import Command, Parameter
from gway.dispatcher import _fill_required_options


def _issue_command() -> Command:
    return Command(
        ("issue",),
        parameters=(
            Parameter("project", required=True, positional=True, annotation=str),
            Parameter("text", required=True, positional=True, annotation=str),
        ),
    )


def test_interactive_fills_all_missing_required_positionals(monkeypatch, capsys) -> None:
    answers = iter(["request", "LCD write fails"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    assert _fill_required_options(_issue_command(), []) == ["request", "LCD write fails"]
    captured = capsys.readouterr()
    assert "project: " in captured.err
    assert "text: " in captured.err


def test_interactive_keeps_provided_positional_and_prompts_for_rest(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda: "LCD write fails")

    assert _fill_required_options(_issue_command(), ["request"]) == ["request", "LCD write fails"]
    captured = capsys.readouterr()
    assert "project: " not in captured.err
    assert "text: " in captured.err


def test_global_flags_stop_at_end_of_options_marker() -> None:
    args, json_output, interactive = _extract_global_flags(
        ["service", "status", "--", "-i", "--json"]
    )

    assert args == ["service", "status", "--", "-i", "--json"]
    assert json_output is False
    assert interactive is False


def test_global_interactive_flag_can_appear_after_managed_command() -> None:
    args, json_output, interactive = _extract_global_flags(["request", "issue", "-i"])

    assert args == ["request", "issue"]
    assert json_output is False
    assert interactive is True
