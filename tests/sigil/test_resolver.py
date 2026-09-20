import pytest

from gway.sigil import Sigil
from gway.sigil.resolver import Environment, Resolver


def test_context_lookup(gateway):
    gateway.context["site"] = "MTY"
    assert gateway.resolve("[site]") == "MTY"


def test_environment_is_a_resolver_source(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_SITE", "Monterrey")
    assert gateway.resolve("[GWAY_TEST_SITE]") == "Monterrey"


def test_unresolved_sigil_raises(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[does_not_exist]")


def test_result_precedes_context_and_environment(gateway, monkeypatch):
    monkeypatch.setenv("CHARGER", "environment")
    gateway.context["charger"] = "context"
    gateway.results.insert("charger", "result")
    assert gateway.resolve("[charger]") == "result"


def test_context_precedes_environment(gateway, monkeypatch):
    monkeypatch.setenv("SITE", "environment")
    gateway.context["site"] = "context"
    assert gateway.resolve("[site]") == "context"


def test_gateway_modulo_resolves_sigil_instance(gateway):
    gateway.context["site"] = "MTY"
    assert gateway % Sigil("site") == "MTY"


def test_gateway_modulo_resolves_sigil_text(gateway):
    gateway.context["site"] = "MTY"
    assert gateway % "[site]" == "MTY"


def test_environment_normalization_belongs_to_environment_source(monkeypatch):
    monkeypatch.setenv("SITE", "environment")

    resolver = Resolver([("config", Environment())])

    assert resolver.find_value("site") == "environment"


def test_source_names_do_not_change_resolution_behavior():
    resolver = Resolver([("env", {"site": "literal"})])

    assert resolver.find_value("site") == "literal"


def test_gway_prefix_is_ordinary_semantic_data(gateway):
    gateway.context["gway"] = {"site": "MTY"}

    assert gateway.resolve("[gway site]") == "MTY"


def test_resolver_does_not_fall_back_to_its_own_attributes(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[resolve]")


def test_none_is_a_resolved_semantic_value(gateway):
    gateway.context["optional"] = None

    assert gateway.resolve("[optional]") is None
    assert gateway.resolve("[optional|fallback]") is None


def test_literal_raise_default_is_not_internal_control_value(gateway):
    assert gateway.resolve("[missing]", default="_raise") == "_raise"
