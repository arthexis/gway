from types import SimpleNamespace

from gway.ingestion.python import discover_python, ingest_python


def test_ingest_plain_function(gateway):
    def ping():
        return "pong"

    wrapped = ingest_python(gateway, ping)

    assert len(wrapped) >= 1
    assert gateway.ops.resolve("ping")() == "pong"


def test_ingest_instance_bound_methods(gateway):
    class Client:
        def start(self, service):
            return f"start:{service}"

    client = Client()
    ingest_python(gateway, client, path=("client",))

    assert gateway("client start arthexis") == "start:arthexis"


def test_ingest_class_discovers_public_methods(gateway):
    class Tools:
        @staticmethod
        def ping():
            return "pong"

    ingest_python(gateway, Tools, path=("tools",))

    assert gateway("tools ping") == "pong"


def test_ingest_nested_object_hierarchy(gateway):
    class Service:
        def status(self):
            return "running"

    root = SimpleNamespace(system=SimpleNamespace(service=Service()))
    ingest_python(gateway, root, path=("root",))

    assert gateway("root system service status") == "running"


def test_repeated_object_reference_is_expanded_only_once():
    class Child:
        def ping(self):
            return "pong"

    child = Child()
    root = SimpleNamespace(left=child, right=child)

    discovered = discover_python(root, path=("root",))
    names = {operation.name for operation in discovered}

    assert "root.left.ping" in names
    assert "root.right.ping" not in names


def test_recursive_cycle_terminates_and_keeps_callable(gateway):
    class Node:
        def ping(self):
            return "pong"

    node = Node()
    node.self = node

    ingest_python(gateway, node, path=("node",))

    assert gateway("node ping") == "pong"


def test_callable_object_itself_is_registered(gateway):
    class Greeter:
        def __call__(self, name):
            return f"hello:{name}"

    greeter = Greeter()
    ingest_python(gateway, greeter, path=("greet",))

    assert gateway("greet Rafael") == "hello:Rafael"


def test_private_members_are_not_walked(gateway):
    class Client:
        def public(self):
            return "public"

        def _private(self):
            return "private"

    ingest_python(gateway, Client(), path=("client",))

    assert gateway("client public") == "public"
    assert gateway.ops.resolve("client._private") is None


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
