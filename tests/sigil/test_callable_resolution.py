import inspect

import pytest

from gway.sigil import Resolver


def test_resolver_find_value_has_no_exec_switch():
    assert "exec" not in inspect.signature(Resolver.find_value).parameters


def test_resolver_has_no_legacy_callable_executor():
    assert not hasattr(Resolver, "_resolve_callable_legacy")


def test_resolver_does_not_execute_callable_values(gateway):
    calls = []

    def value():
        calls.append("called")
        return "result"

    gateway.context["value"] = value

    assert gateway.find_value("value") is value
    assert calls == []


def test_dispatch_does_not_execute_plain_callable_context_values(gateway):
    gateway.context["ping"] = lambda: "pong"

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway("ping")
