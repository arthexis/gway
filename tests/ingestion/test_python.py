from types import SimpleNamespace

from gway.ingestion.python import discover_python, ingest_python


def test_ingest_plain_function(gateway):
    def ping():
        return "pong"

    wrapped = ingest_python(gateway, ping)

    assert len(wrapped) == 1
    assert gateway.ops.resolve("ping")() == "pong"


def test_ingest_instance_expands_only_direct_public_methods(gateway):
    class Child:
        def ping(self):
            return "pong"

    class Client:
        def start(self, service):
            return f"start:{service}"

    client = Client()
    client.child = Child()
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


def test_nested_object_hierarchy_expands_one_level_at_a_time(gateway):
    class Service:
        def status(self):
            return "running"

    service = Service()
    system = SimpleNamespace(service=service)
    root = SimpleNamespace(system=system)

    ingest_python(gateway, root, path=("root",))
    assert gateway.ops.resolve("root.system.service.status") is None

    ingest_python(gateway, system, path=("root", "system"))
    assert gateway.ops.resolve("root.system.service.status") is None

    ingest_python(gateway, service, path=("root", "system", "service"))
    assert gateway("root system service status") == "running"


def test_seen_child_can_be_expanded_later(gateway):
    class Child:
        def ping(self):
            return "pong"

    child = Child()
    root = SimpleNamespace(child=child)

    ingest_python(gateway, root, path=("root",))
    record = gateway._ingested[id(child)]

    assert record.expanded is False
    assert record.registered is False
    assert ("root", "child") in record.paths

    ingest_python(gateway, child, path=("root", "child"))

    assert record.expanded is True
    assert gateway("root child ping") == "pong"


def test_reingesting_expanded_object_is_noop(gateway):
    root = SimpleNamespace()
    root.ping = lambda: "pong"

    first = ingest_python(gateway, root, path=("root",))
    second = ingest_python(gateway, root, path=("root",))

    assert len(first) == 1
    assert second == []
    assert gateway("root ping") == "pong"


def test_repeated_reference_is_remembered_once_by_identity(gateway):
    child = SimpleNamespace()
    root = SimpleNamespace(left=child, right=child)

    ingest_python(gateway, root, path=("root",))

    record = gateway._ingested[id(child)]
    assert record.value is child
    assert record.paths == {("root", "left"), ("root", "right")}
    assert record.expanded is False


def test_cycle_is_seen_without_recursive_expansion(gateway):
    class Node:
        def ping(self):
            return "pong"

    node = Node()
    node.self = node

    ingest_python(gateway, node, path=("node",))

    assert gateway("node ping") == "pong"
    assert gateway._ingested[id(node)].expanded is True
    assert ("node", "self") in gateway._ingested[id(node)].paths


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


def test_discover_python_is_one_level_only():
    class Child:
        def ping(self):
            return "pong"

    root = SimpleNamespace(child=Child())
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
