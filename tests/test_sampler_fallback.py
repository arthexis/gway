import pytest

from gway import Gateway


def test_bare_gateway_does_not_eagerly_register_app_operations():
    gateway = Gateway()

    assert gateway.ops.resolve("setup.app") is None
    assert gateway.ops.resolve("serve.app") is None
    assert gateway.ops.resolve("expose.app") is None


def test_sampler_fallback_loads_app_only_after_resolution_miss():
    gateway = Gateway()

    app = gateway("setup app remote")

    assert app.name == "remote"
    assert gateway.ops.resolve("setup.app") is not None
    assert gateway.ops.resolve("view.app") is not None
    assert gateway.ops.resolve("expose.app") is not None


def test_existing_operation_wins_before_sampler_fallback():
    gateway = Gateway()
    calls = []

    def setup_app(name=None):
        calls.append(name)
        return "builtin-wins"

    gateway.wrap("setup.app", setup_app, op="setup", sub="app")

    assert gateway("setup app remote") == "builtin-wins"
    assert calls == ["remote"]
    assert getattr(gateway, "_sampler_routes", set()) == set()


def test_sampler_fallback_is_not_reloaded_after_first_use():
    gateway = Gateway()

    first = gateway("setup app remote")
    loaded = set(gateway._sampler_routes)
    second = gateway("setup app second")

    assert first.name == "remote"
    assert second.name == "second"
    assert gateway._sampler_routes == loaded
