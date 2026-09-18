import pytest

from gway import Sigil
from gway.binding import Literal
from gway.normalization import complete_arguments


def test_explicit_arguments_are_preserved(gateway):
    def create_charger(limit: int):
        return limit

    call = complete_arguments(
        gateway,
        "charger",
        create_charger,
        args=("32",),
    )
    assert call.args == ("32",)


def test_python_default_is_completed(gateway):
    def create_charger(serial: str = "DEFAULT"):
        return serial

    call = complete_arguments(gateway, "charger", create_charger)
    assert call.args == ("DEFAULT",)


def test_subject_argument_is_injected_from_runtime(gateway):
    gateway.context["charger"] = "CHG001"

    def inspect_charger(charger):
        return charger

    call = complete_arguments(gateway, "charger", inspect_charger)
    assert call.args == ("CHG001",)


def test_sigil_default_resolves_against_runtime(gateway):
    gateway.context["serial"] = "ABC"

    def create_charger(serial=Sigil("[serial]")):
        return serial

    call = complete_arguments(gateway, "charger", create_charger)
    assert call.args == ("ABC",)


def test_missing_required_argument_fails_after_semantic_completion(gateway):
    def create_charger(serial: str):
        return serial

    with pytest.raises(TypeError, match="missing required argument"):
        complete_arguments(gateway, "charger", create_charger)


def test_literal_marker_is_unwrapped_without_type_coercion(gateway):
    def create_charger(limit: int):
        return limit

    call = complete_arguments(
        gateway,
        "charger",
        create_charger,
        args=(Literal("32"),),
    )
    assert call.args == ("32",)
