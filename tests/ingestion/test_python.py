from types import SimpleNamespace

from gway.ingestion.python import discover_python, ingest_python


def test_ingest_plain_function(gateway):
    def ping():
        return "pong"

    wrapped = ingest_python(gateway, ping)

    assert len(wrapped) == 1
    assert gateway.ops.resolve("ping")() == "pong"


def test_ingest_instance_expands_only_direct_public_methods(gateway, make_ping_node):
    class Client:
        def start(self, service):
            return f"start:{service}"

    client = Client()
    client.child = make_ping_node()
    ingest_python(gateway, client, path=("client",))

    assert gateway("client start arthexis") == "start:arthexis"
    assert gateway.ops.resolve("client.child.ping") is None


def test_ingest_class_discovers_direct_public_methods(gateway):
    class Tools:
        @staticmethod
        def ping():
            return "pong"

    ingest_python(gateway, Tools, path=("tools",))

    assert gateway("tools ping") == "pong"


def test_nested_object_hierarchy_expands_one_level_at_a_time(gateway, make_ping_node):
    service = make_ping_node("running")
    system = SimpleNamespace(service=service)
    root = SimpleNamespace(system=system)

    ingest_python(gateway, root, path=("root",))
    assert gateway.ops.resolve("root.system.service.ping") is None

    ingest_python(gateway, system, path=("root", "system"))
    assert gateway.ops.resolve("root.system.service.ping") is None

    ingest_python(gateway, service, path=("root", "system", "service"))
    assert gateway("root system service ping") == "running"


def test_callable_object_itself_is_registered(gateway):
    class Greeter:
        def __call__(self, name):
            return f"hello:{name}"

    greeter = Greeter()
    ingest_python(gateway, greeter, path=("greet",))

    assert gateway("greet Rafael") == "hello:Rafael"


def test_private_members_are_skipped(gateway):
    class Client:
        def public(self):
            return "public"

        def _private(self):
            return "private"

    ingest_python(gateway, Client(), path=("client",))

    assert gateway("client public") == "public"
    assert gateway.ops.resolve("client._private") is None


def test_discover_python_is_one_level_only(make_ping_node):
    root = SimpleNamespace(child=make_ping_node())
    root.run = lambda: "run"

    names = {item.name for item in discover_python(root, path=("root",))}

    assert "root.run" in names
    assert "root.child.ping" not in names


def test_discovered_operations_preserve_python_provenance():
    class Client:
        def status(self):
            return "ok"

    client = Client()
    discovered = discover_python(client, path=("client",))
    status = next(item for item in discovered if item.name == "client.status")

    assert status.source is client
    assert status.kind == "python"
    assert status.metadata["object"].__self__ is client


def test_module_dunder_main_represents_module_operation(gateway):
    from types import ModuleType

    module = ModuleType("demo")

    def __main__(value):
        return f"main:{value}"

    def info(value):
        return f"info:{value}"

    module.__main__ = __main__
    module.info = info

    ingest_python(gateway, module, path=("demo",))

    assert gateway("demo value") == "main:value"
    assert gateway("demo info value") == "info:value"
    assert gateway.ops["demo"][None].__wrapped__ is __main__
    assert gateway.ops["demo"]["info"].__wrapped__ is info
