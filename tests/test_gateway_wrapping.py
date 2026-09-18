import asyncio

import pytest

from gway import Sigil


def test_subject_uses_verb_subject_vocabulary():
    from gway import Gateway

    assert Gateway.subject("create_charger") == "charger"
    assert Gateway.subject("device.create_charger") == "charger"


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

    wrapped = gateway.wrap_callable("create_charger", create_charger)
    assert wrapped("32") == 32


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

    wrapped = gateway.wrap_callable("inspect_charger", inspect_charger)
    assert wrapped() == "CHG001"


def test_scalar_result_publishes_under_subject(gateway):
    def get_charger():
        return "CHG001"

    wrapped = gateway.wrap_callable("get_charger", get_charger)
    assert wrapped() == "CHG001"
    assert gateway.results["charger"] == "CHG001"


def test_mapping_result_is_merged_into_context(gateway):
    def inspect_charger():
        return {"serial": "CHG001", "online": True}

    wrapped = gateway.wrap_callable("inspect_charger", inspect_charger)
    wrapped()
    assert gateway.context["serial"] == "CHG001"
    assert gateway.context["online"] is True


def test_sigil_default_resolves_at_call_time(gateway):
    gateway.context["serial"] = "ABC"

    def create_charger(serial=Sigil("[serial]")):
        return serial

    wrapped = gateway.wrap_callable("create_charger", create_charger)
    assert wrapped() == "ABC"


def test_async_callable_runs(gateway):
    async def get_charger():
        await asyncio.sleep(0)
        return "ASYNC"

    wrapped = gateway.wrap_callable("get_charger", get_charger)
    assert wrapped() == "ASYNC"
