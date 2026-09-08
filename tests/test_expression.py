from __future__ import annotations

import pytest

from gway.expression import ExpressionError, normalize_managed_args


def test_space_syntax_is_preserved() -> None:
    project, args = normalize_managed_args(["health", "errors"])
    assert project == "health"
    assert args == ["errors"]


def test_dotted_project_command_syntax() -> None:
    project, args = normalize_managed_args(["health.errors"])
    assert project == "health"
    assert args == ["errors"]


def test_dotted_nested_command_syntax() -> None:
    project, args = normalize_managed_args(["charger.connector.status"])
    assert project == "charger"
    assert args == ["connector", "status"]


def test_dotted_command_after_separate_project() -> None:
    project, args = normalize_managed_args(["charger", "connector.status"])
    assert project == "charger"
    assert args == ["connector", "status"]


def test_trailing_colon_is_explicit_but_argument_free() -> None:
    project, args = normalize_managed_args(["health.errors:"])
    assert project == "health"
    assert args == ["errors"]


def test_colon_argument_becomes_normal_dispatch_argument() -> None:
    project, args = normalize_managed_args(["charger.status:1"])
    assert project == "charger"
    assert args == ["status", "1"]


def test_remaining_cli_arguments_follow_compact_expression() -> None:
    project, args = normalize_managed_args(["charger.status:1", "--verbose"])
    assert project == "charger"
    assert args == ["status", "1", "--verbose"]


@pytest.mark.parametrize("expression", [".health", "health.", "health..errors", ":arg"])
def test_invalid_compact_paths_are_rejected(expression: str) -> None:
    with pytest.raises(ExpressionError):
        normalize_managed_args([expression])
