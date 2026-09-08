from __future__ import annotations

from gway.command import Command, Parameter
from gway.dispatcher import _decode_structured_argv
from gway.expression import STRUCTURED_ARG_PREFIX, STRUCTURED_KWARG_PREFIX


def _command() -> Command:
    return Command(
        path=("probe",),
        parameters=(
            Parameter("interface", required=True, positional=True, annotation=str),
            Parameter("metric", required=False, positional=False, annotation=str, default="state"),
            Parameter("verbose", required=False, positional=False, annotation=bool, default=False),
        ),
    )


def test_structured_positional_binds_in_parameter_order() -> None:
    argv = _decode_structured_argv(
        _command(),
        [f"{STRUCTURED_ARG_PREFIX}wlan0", f"{STRUCTURED_ARG_PREFIX}count"],
    )
    assert argv == ["wlan0", "--metric", "count"]


def test_structured_keyword_can_fill_required_positional_parameter() -> None:
    argv = _decode_structured_argv(
        _command(),
        [f"{STRUCTURED_KWARG_PREFIX}interface=wlan0"],
    )
    assert argv == ["wlan0"]


def test_structured_keyword_uses_normal_option_for_optional_parameter() -> None:
    argv = _decode_structured_argv(
        _command(),
        [
            f"{STRUCTURED_KWARG_PREFIX}interface=wlan0",
            f"{STRUCTURED_KWARG_PREFIX}metric=count",
        ],
    )
    assert argv == ["wlan0", "--metric", "count"]


def test_structured_boolean_keyword_uses_boolean_option() -> None:
    argv = _decode_structured_argv(
        _command(),
        [
            f"{STRUCTURED_KWARG_PREFIX}interface=wlan0",
            f"{STRUCTURED_KWARG_PREFIX}verbose=true",
        ],
    )
    assert argv == ["wlan0", "--verbose"]


def test_comma_value_remains_one_dispatch_value() -> None:
    argv = _decode_structured_argv(
        _command(),
        [f"{STRUCTURED_ARG_PREFIX}wlan0,eth0"],
    )
    assert argv == ["wlan0,eth0"]
