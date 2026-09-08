from __future__ import annotations

from gway.command import Command, Parameter
from gway.dispatcher import _decode_structured_argv, _fill_required_options
from gway.expression import STRUCTURED_KWARG_PREFIX


def test_interactive_recognizes_unambiguous_long_option_abbreviation(monkeypatch) -> None:
    command = Command(
        ("example",),
        parameters=(
            Parameter(
                "target",
                options=("--target",),
                consumes_value=True,
            ),
            Parameter("project", required=True, positional=True, annotation=str),
        ),
    )
    monkeypatch.setattr("builtins.input", lambda: "request")

    assert _fill_required_options(command, ["--targ", "lcd"]) == [
        "--targ",
        "lcd",
        "request",
    ]


def test_interactive_prompts_for_missing_structured_positional_arity(monkeypatch) -> None:
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
    first = f"{STRUCTURED_KWARG_PREFIX}pair=one"
    monkeypatch.setattr("builtins.input", lambda: "two")

    completed = _fill_required_options(command, [first])

    assert completed == [first, f"{STRUCTURED_KWARG_PREFIX}pair=two"]
    assert _decode_structured_argv(command, completed) == ["one", "two"]


def test_interactive_terminates_variadic_option_with_structured_binding(monkeypatch) -> None:
    command = Command(
        ("issue",),
        parameters=(
            Parameter(
                "labels",
                options=("--labels",),
                consumes_value=True,
                option_arity="+",
            ),
            Parameter("project", required=True, positional=True, annotation=str),
            Parameter("text", required=True, positional=True, annotation=str),
        ),
    )
    text = f"{STRUCTURED_KWARG_PREFIX}text=hello"
    monkeypatch.setattr("builtins.input", lambda: "request")

    completed = _fill_required_options(command, ["--labels", "a", text])

    assert completed == ["--labels", "a", text, "--", "request"]
    assert _decode_structured_argv(command, completed) == [
        "--labels",
        "a",
        "--",
        "request",
        "hello",
    ]
