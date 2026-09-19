import pytest

from gway import Sigil


def test_required_argument_failure(gateway):
    def create_charger(serial: str):
        return serial

    wrapped = gateway.wrap("create_charger", create_charger)
    with pytest.raises(TypeError, match="missing required argument"):
        wrapped()


def test_python_default_is_preserved(gateway):
    def create_charger(serial: str = "DEFAULT"):
        return serial

    wrapped = gateway.wrap("create_charger", create_charger)
    assert wrapped() == "DEFAULT"


def test_direct_python_argument_is_not_retyped(gateway):
    def create_charger(limit: int):
        return limit

    wrapped = gateway.wrap("create_charger", create_charger)
    assert wrapped("32") == "32"


def test_subject_argument_is_injected_from_context(gateway):
    gateway.context["charger"] = "CHG001"

    def inspect_charger(charger):
        return charger

    assert gateway.wrap("inspect_charger", inspect_charger)() == "CHG001"


def test_sigil_default_resolves_at_call_time(gateway):
    gateway.context["serial"] = "ABC"

    def create_charger(serial=Sigil("[serial]")):
        return serial

    assert gateway.wrap("create_charger", create_charger)() == "ABC"


def test_semantic_completion_preserves_explicit_none_result(gateway):
    gateway.results.insert("charger", None)

    def inspect_charger(charger="fallback"):
        return charger

    wrapped = gateway.wrap("inspect_charger", inspect_charger)

    assert wrapped() is None


def test_missing_positional_parameter_is_completed_by_its_name(gateway):
    gateway.context["chargers"] = ["A", "B"]

    def summarize(items, chargers):
        return items, chargers

    wrapped = gateway.wrap("summarize_report", summarize)

    assert wrapped("ready") == ("ready", ["A", "B"])


def test_positional_only_parameter_can_be_completed_by_semantic_name(gateway):
    gateway.context["chargers"] = ["A", "B"]

    def summarize(chargers, /):
        return chargers

    wrapped = gateway.wrap("summarize_report", summarize)

    assert wrapped() == ["A", "B"]


def test_explicit_argument_precedes_named_semantic_completion(gateway):
    gateway.context["chargers"] = ["context"]

    def summarize(chargers):
        return chargers

    wrapped = gateway.wrap("summarize_report", summarize)

    assert wrapped(["explicit"]) == ["explicit"]
