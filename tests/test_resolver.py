from types import SimpleNamespace

import pytest


def test_context_lookup(gateway):
    gateway.context["site"] = "MTY"
    assert gateway.resolve("[site]") == "MTY"


def test_result_precedes_context_and_environment(gateway, monkeypatch):
    monkeypatch.setenv("CHARGER", "environment")
    gateway.context["charger"] = "context"
    gateway.results.insert("charger", "result")
    assert gateway.resolve("[charger]") == "result"


def test_context_precedes_environment(gateway, monkeypatch):
    monkeypatch.setenv("SITE", "environment")
    gateway.context["site"] = "context"
    assert gateway.resolve("[site]") == "context"


def test_environment_is_a_resolver_source(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_SITE", "Monterrey")
    assert gateway.resolve("[GWAY_TEST_SITE]") == "Monterrey"


def test_nested_mapping_and_sequence_traversal(gateway):
    gateway.context["response"] = {
        "payload": {"chargers": [{"serial": "A"}, {"serial": "B"}]}
    }
    assert gateway.resolve("[response payload chargers 1 serial]") == "B"


def test_object_attribute_traversal(gateway):
    gateway.context["charger"] = SimpleNamespace(serial="ABC")
    assert gateway.resolve("[charger serial]") == "ABC"


def test_unresolved_sigil_raises(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[does_not_exist]")


def test_quoted_sigil_is_exact_lookup_not_literal(gateway):
    gateway.context["status code"] = 200
    assert gateway.resolve('["status code"]') == 200

    with pytest.raises(KeyError):
        gateway.resolve('["missing key"]')
