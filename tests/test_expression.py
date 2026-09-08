from __future__ import annotations

import pytest

from gway.expression import (
    MANAGED_EXPRESSION_PROJECT,
    ExpressionError,
    normalize_managed_args,
    parse_managed_branches,
)


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


def test_trailing_colon_routes_to_literal_expression() -> None:
    project, args = normalize_managed_args(["health.errors:"])
    assert project == MANAGED_EXPRESSION_PROJECT
    assert args == ["health.errors:"]
    branch = parse_managed_branches(args[0])[0]
    assert branch.is_literal
    assert branch.literal == "health.errors"


def test_colon_argument_becomes_normal_dispatch_argument() -> None:
    project, args = normalize_managed_args(["charger.status:1"])
    assert project == "charger"
    assert args == ["status", "1"]


def test_remaining_cli_arguments_follow_compact_expression() -> None:
    project, args = normalize_managed_args(["charger.status:1", "--verbose"])
    assert project == "charger"
    assert args == ["status", "1", "--verbose"]


def test_fallback_expression_routes_to_dispatcher_expression_mode() -> None:
    expression = "health.errors|backup.errors|:offline"
    project, args = normalize_managed_args([expression])
    assert project == MANAGED_EXPRESSION_PROJECT
    assert args == [expression]


def test_fallback_branches_preserve_commands_and_terminal_literal() -> None:
    branches = parse_managed_branches("health.errors|backup status|:offline")
    assert branches[0].project == "health"
    assert branches[0].args == ("errors",)
    assert branches[1].project == "backup"
    assert branches[1].args == ("status",)
    assert branches[2].is_literal
    assert branches[2].literal == "offline"


def test_trailing_literal_stops_fallback_chain() -> None:
    branches = parse_managed_branches("health.errors|standby:|ignored.value")
    assert len(branches) == 2
    assert branches[1].literal == "standby"


@pytest.mark.parametrize("expression", [".health", "health.", "health..errors", ":arg"])
def test_invalid_compact_paths_are_rejected(expression: str) -> None:
    with pytest.raises(ExpressionError):
        normalize_managed_args([expression])
