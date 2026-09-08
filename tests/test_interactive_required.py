from __future__ import annotations

from gway.cli import _extract_global_flags
from gway.command import Command, Parameter
from gway.dispatcher import _decode_structured_argv, _fill_required_options
from gway.expression import STRUCTURED_KWARG_PREFIX


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


def test_interactive_preserves_named_later_positional_binding(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda: "request")
    text = f"{STRUCTURED_KWARG_PREFIX}text=LCD write fails"

    completed = _fill_required_options(_issue_command(), [text])

    assert _decode_structured_argv(_issue_command(), completed) == ["request", "LCD write fails"]
    captured = capsys.readouterr()
    assert "project: " in captured.err
    assert "text: " not in captured.err


def test_structured_tokens_after_end_of_options_are_literal() -> None:
    token = f"{STRUCTURED_KWARG_PREFIX}text=literal"
    assert _decode_structured_argv(_issue_command(), ["--", token]) == ["--", token]


def test_interactive_terminates_trailing_variadic_option(monkeypatch) -> None:
    command = Command(
        ("example",),
        parameters=(
            Parameter(
                "labels",
                options=("--labels",),
                consumes_value=True,
                option_arity="+",
            ),
            Parameter("project", required=True, positional=True, annotation=str),
        ),
    )
    monkeypatch.setattr("builtins.input", lambda: "request")

    assert _fill_required_options(command, ["--labels", "a", "b"]) == [
        "--labels",
        "a",
        "b",
        "--",
        "request",
    ]


def test_interactive_prompts_for_remaining_fixed_positional_arity(monkeypatch) -> None:
    command = Command(
        ("example",),
        parameters=(
            Parameter(
                "pair",
                required=True,
                positional=True,
                annotation=str,
                option_arity=2,
            ),
        ),
    )
    monkeypatch.setattr("builtins.input", lambda: "two")

    assert _fill_required_options(command, ["one"]) == ["one", "two"]


def test_attached_short_option_value_is_not_counted_as_positional(monkeypatch) -> None:
    command = Command(
        ("example",),
        parameters=(
            Parameter(
                "target",
                options=("-t", "--target"),
                consumes_value=True,
            ),
            Parameter("project", required=True, positional=True, annotation=str),
        ),
    )
    monkeypatch.setattr("builtins.input", lambda: "request")

    assert _fill_required_options(command, ["-tfoo"]) == ["-tfoo", "request"]


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
