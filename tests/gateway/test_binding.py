import pytest

from gway import Sigil


def test_required_argument_failure(gateway):
    def create_charger(serial: str):
        return serial
    wrapped = gateway.wrap_callable("create_charger", create_charger)
    with pytest.raises(TypeError, match="missing required argument"):
        wrapped()


def test_python_default_is_preserved(gateway):
    def create_charger(serial: str = "DEFAULT"):
        return serial
    wrapped = gateway.wrap_callable("create_charger", create_charger)
    assert wrapped() == "DEFAULT"


def test_primitive_type_coercion(gateway):
    def create_charger(limit: int):
        return limit
    assert gateway.wrap_callable("create_charger", create_charger)("32") == 32


def test_boolean_type_coercion(gateway):
    def create_charger(enabled: bool):
        return enabled
    wrapped = gateway.wrap_callable("create_charger", create_charger)
    assert wrapped("yes") is True
    assert wrapped("off") is False


def test_subject_argument_is_injected_from_context(gateway):
    gateway.context["charger"] = "CHG001"
    def inspect_charger(charger):
        return charger
    assert gateway.wrap_callable("inspect_charger", inspect_charger)() == "CHG001"


def test_sigil_default_resolves_at_call_time(gateway):
    gateway.context["serial"] = "ABC"
    def create_charger(serial=Sigil("[serial]")):
        return serial
    assert gateway.wrap_callable("create_charger", create_charger)() == "ABC"
