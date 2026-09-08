from __future__ import annotations

import pytest

from gway.expression import (
    MANAGED_EXPRESSION_PROJECT,
    STRUCTURED_ARG_PREFIX,
    STRUCTURED_KWARG_PREFIX,
    STRUCTURED_TUPLE_PREFIX,
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


def test_colon_argument_routes_through_expression_mode() -> None:
    project, args = normalize_managed_args(["charger.status:1"])
    assert project == MANAGED_EXPRESSION_PROJECT
    assert args == ["charger.status:1"]
    branch = parse_managed_branches(args[0])[0]
    assert branch.project == "charger"
    assert branch.args == ("status", f"{STRUCTURED_ARG_PREFIX}1")


def test_spaced_colon_positional_argument() -> None:
    project, args = normalize_managed_args(["network", "ip", ":", "wlan0"])
    assert project == MANAGED_EXPRESSION_PROJECT
    branch = parse_managed_branches(args[0])[0]
    assert branch.project == "network"
    assert branch.args == ("ip", f"{STRUCTURED_ARG_PREFIX}wlan0")


def test_keyword_argument_is_preserved_for_command_aware_binding() -> None:
    branch = parse_managed_branches("network ip : interface = wlan0")[0]
    assert branch.args == (
        "ip",
        f"{STRUCTURED_KWARG_PREFIX}interface=wlan0",
    )


def test_explicit_positional_colon_equals() -> None:
    branch = parse_managed_branches("echo := left=right")[0]
    assert branch.args == ("echo", f"{STRUCTURED_ARG_PREFIX}left=right")


def test_multiple_colons_create_multiple_arguments() -> None:
    branch = parse_managed_branches("demo combine : first : second : mode=fast")[0]
    assert branch.args == (
        "combine",
        f"{STRUCTURED_ARG_PREFIX}first",
        f"{STRUCTURED_ARG_PREFIX}second",
        f"{STRUCTURED_KWARG_PREFIX}mode=fast",
    )


def test_commas_create_grouped_tuple_arguments() -> None:
    branch = parse_managed_branches("demo shape : a , b , c : values = x , y")[0]
    assert branch.args == (
        "shape",
        f"{STRUCTURED_ARG_PREFIX}{STRUCTURED_TUPLE_PREFIX}a,b,c",
        f"{STRUCTURED_KWARG_PREFIX}values={STRUCTURED_TUPLE_PREFIX}x,y",
    )


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
