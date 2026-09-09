from __future__ import annotations

import pytest

from gway.stage import (
    StageKind,
    StageSyntaxError,
    classify_stage,
    decode_bracket_escapes,
    parse_stages,
    split_stage_tokens,
)


def test_split_stage_tokens_uses_only_standalone_dash() -> None:
    assert split_stage_tokens(["alpha", "user-name", "-", "beta", "-i"]) == (
        ("alpha", "user-name"),
        ("beta", "-i"),
    )


def test_literal_boundary_preserves_subsequent_dash() -> None:
    assert split_stage_tokens(["alpha", "--", "-", "beta"]) == (("alpha", "--", "-", "beta"),)


def test_bracket_dash_does_not_split_stage() -> None:
    stages = parse_stages(["%", "left", "[-]", "right", "-", "upper"])

    assert stages[0].kind is StageKind.SOLVE
    assert stages[0].tokens == ("left", "-", "right")
    assert stages[0].raw_tokens == ("left", "[-]", "right")
    assert stages[1].kind is StageKind.COMMAND
    assert stages[1].tokens == ("upper",)


def test_doubled_brackets_escape_literal_brackets() -> None:
    assert decode_bracket_escapes("[[name]]") == "[name]"
    assert decode_bracket_escapes("prefix-[[name]]-suffix") == "prefix-[name]-suffix"
    assert decode_bracket_escapes("[[-]]") == "[-]"


def test_adjacent_bracket_escapes_do_not_overlap() -> None:
    assert decode_bracket_escapes("[-]]]") == "-]"
    assert decode_bracket_escapes("[[]]") == "[]"
    assert decode_bracket_escapes("[[-]][-]]]") == "[-]-]"


def test_leading_percent_is_explicit_solve_marker() -> None:
    stage = classify_stage(["%", "hello", "[name]"])

    assert stage.kind is StageKind.SOLVE
    assert stage.explicit_solve is True
    assert stage.tokens == ("hello", "[name]")
    assert stage.raw_tokens == ("hello", "[name]")


def test_percent_after_first_token_is_literal() -> None:
    stage = classify_stage(["command", "50", "%"])

    assert stage.kind is StageKind.COMMAND
    assert stage.explicit_solve is False
    assert stage.tokens == ("command", "50", "%")


def test_percent_inside_solve_template_is_literal() -> None:
    stage = classify_stage(["%", "Battery", "at", "50", "%"])

    assert stage.kind is StageKind.SOLVE
    assert stage.tokens == ("Battery", "at", "50", "%")


def test_bracket_leading_stage_is_implicit_solve() -> None:
    stage = classify_stage(["[name]", "is", "online"])

    assert stage.kind is StageKind.SOLVE
    assert stage.explicit_solve is False
    assert stage.tokens == ("[name]", "is", "online")


def test_bracket_escape_does_not_trigger_implicit_solve() -> None:
    stage = classify_stage(["[[name]]", "literal"])

    assert stage.kind is StageKind.COMMAND
    assert stage.tokens == ("[name]", "literal")
    assert stage.raw_tokens == ("[[name]]", "literal")


def test_bare_name_is_command_stage() -> None:
    assert classify_stage(["name"]).kind is StageKind.COMMAND


def test_empty_chain_stages_are_rejected() -> None:
    with pytest.raises(StageSyntaxError, match="empty stage"):
        split_stage_tokens(["alpha", "-", "-", "beta"])

    with pytest.raises(StageSyntaxError, match="empty stage"):
        split_stage_tokens(["alpha", "-"])


def test_percent_only_stage_requires_template() -> None:
    with pytest.raises(StageSyntaxError, match="requires a template"):
        classify_stage(["%"])
