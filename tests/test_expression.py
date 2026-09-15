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


def test_trailing_colon_is_ordinary_command_data() -> None:
    project, args = normalize_managed_args(["health.errors:"])
    assert project == "health"
    assert args == ["errors:"]


def test_colon_inside_compact_command_is_not_call_syntax() -> None:
    project, args = normalize_managed_args(["charger.status:1"])
    assert project == "charger"
    assert args == ["status:1"]


def test_spaced_colon_is_an_ordinary_argument() -> None:
    project, args = normalize_managed_args(["network", "ip", ":", "wlan0"])
    assert project == "network"
    assert args == ["ip", ":", "wlan0"]


def test_scope_value_with_colon_stays_out_of_expression_mode() -> None:
    project, args = normalize_managed_args(
        ["web", "token", "--scope", "logs:read"]
    )
    assert project == "web"
    assert args == ["token", "--scope", "logs:read"]


def test_urls_times_and_multiple_colons_remain_opaque_arguments() -> None:
    values = [
        "https://logs.arthexis.com/api/logs/run/events",
        "12:30",
        "foo:bar:baz",
    ]
    project, args = normalize_managed_args(["demo", "echo", *values])
    assert project == "demo"
    assert args == ["echo", *values]


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


def test_fallback_command_arguments_keep_colons_as_data() -> None:
    branches = parse_managed_branches(
        "web token --scope logs:read|backup status|:offline"
    )
    assert branches[0].project == "web"
    assert branches[0].args == ("token", "--scope", "logs:read")
    assert branches[1].project == "backup"
    assert branches[1].args == ("status",)
    assert branches[2].literal == "offline"


def test_trailing_colon_does_not_stop_fallback_chain() -> None:
    branches = parse_managed_branches("health.errors|standby:|ignored.value")
    assert len(branches) == 3
    assert branches[1].project == "standby:"
    assert not branches[1].is_literal
    assert branches[2].project == "ignored"
    assert branches[2].args == ("value",)


@pytest.mark.parametrize("expression", [".health", "health.", "health..errors"])
def test_invalid_compact_paths_are_rejected(expression: str) -> None:
    with pytest.raises(ExpressionError):
        normalize_managed_args([expression])
