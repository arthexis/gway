from types import ModuleType, SimpleNamespace

import pytest


def test_python_module_aka_preserves_canonical_root(gateway):
    module = ModuleType("demo.tools")

    def ping():
        return "pong"

    module.ping = ping

    gateway.ingest(module, aka="tools")

    assert gateway.ops.resolve("tools.ping") is gateway.ops.resolve("demo.tools.ping")
    assert gateway("tools ping") == "pong"
    assert gateway("demo tools ping") == "pong"


def test_python_module_aka_preserves_jit_namespace_reachability(gateway):
    module = ModuleType("demo")
    child = SimpleNamespace()

    def ping():
        return "pong"

    child.ping = ping
    module.child = child

    gateway.ingest(module, aka="short")

    assert gateway.ops.resolve("short.child.ping") is None
    assert gateway("short child ping") == "pong"
    assert gateway.ops.resolve("short.child.ping") is not None


def test_python_module_aka_refuses_to_shadow_existing_operation(gateway):
    first = ModuleType("first")
    second = ModuleType("second")

    first.ping = lambda: "first"
    second.ping = lambda: "second"

    gateway.ingest(first, aka="shared")

    with pytest.raises(
        ValueError,
        match="AKA conflicts with existing operation: shared.ping",
    ):
        gateway.ingest(second, aka="shared")
