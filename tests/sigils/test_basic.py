import pytest


def test_context_lookup(gateway):
    gateway.context["site"] = "MTY"
    assert gateway.resolve("[site]") == "MTY"


def test_environment_is_a_resolver_source(gateway, monkeypatch):
    monkeypatch.setenv("GWAY_TEST_SITE", "Monterrey")
    assert gateway.resolve("[GWAY_TEST_SITE]") == "Monterrey"


def test_unresolved_sigil_raises(gateway):
    with pytest.raises(KeyError):
        gateway.resolve("[does_not_exist]")


def test_quoted_sigil_is_exact_lookup_not_literal(gateway):
    gateway.context["status code"] = 200
    assert gateway.resolve('["status code"]') == 200
    with pytest.raises(KeyError):
        gateway.resolve('["missing key"]')
