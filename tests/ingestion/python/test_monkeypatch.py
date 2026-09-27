from types import ModuleType, SimpleNamespace


def test_ingested_module_function_follows_monkeypatch(gateway, monkeypatch):
    module = ModuleType("latebound_demo")

    def greet(name: str):
        return f"hello:{name}"

    module.greet = greet
    gateway.ingest(module)

    assert gateway("latebound_demo greet Rafael") == "hello:Rafael"

    def patched(count: int):
        return count + 1

    monkeypatch.setattr(module, "greet", patched)

    assert gateway("latebound_demo greet 4") == 5


def test_ingested_help_uses_monkeypatched_signature(gateway, monkeypatch):
    module = ModuleType("latebound_help")

    def inspect_value(value: str):
        """Inspect a string value."""
        return value

    module.inspect_value = inspect_value
    gateway.ingest(module)

    def patched(limit: int = 3):
        """Inspect a numeric limit."""
        return limit

    monkeypatch.setattr(module, "inspect_value", patched)

    help_text = gateway._help("latebound_help", "inspect_value", verbose=True)

    assert "(limit: int = 3)" in help_text
    assert "(value: str)" not in help_text


def test_ingested_class_method_follows_monkeypatch(gateway, monkeypatch):
    class Device:
        def status(self, detail: str = "brief"):
            return f"old:{detail}"

    gateway.ingest(Device, path=("device",))
    gateway.context["device"] = Device()

    assert gateway("device status full") == "old:full"

    def patched(self, level: int):
        return level * 2

    monkeypatch.setattr(Device, "status", patched)

    assert gateway("device status 7") == 14


def test_direct_callable_without_stable_owner_keeps_captured_behavior(
    gateway,
    monkeypatch,
):
    def operation(value: str):
        return f"captured:{value}"

    holder = SimpleNamespace(operation=operation)
    wrapped = gateway.wrap("captured.operation", holder.operation)

    def replacement(value: str):
        return f"replacement:{value}"

    monkeypatch.setattr(holder, "operation", replacement)

    assert wrapped("x") == "captured:x"
