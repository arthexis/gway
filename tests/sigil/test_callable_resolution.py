import pytest


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
