from types import SimpleNamespace

from gway.ingestion.python import ingest_python


def test_seen_child_can_be_expanded_later(gateway, make_ping_node):
    child = make_ping_node()
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


def test_cycle_is_seen_without_recursive_expansion(gateway, make_ping_node):
    node = make_ping_node()
    node.self = node

    ingest_python(gateway, node, path=("node",))

    record = gateway._ingested[id(node)]
    assert gateway("node ping") == "pong"
    assert record.expanded is True
    assert ("node", "self") in record.paths


def test_jiti_updates_only_requested_branch_state(gateway, make_ping_node):
    leaf = make_ping_node()
    child = SimpleNamespace(grandchild=leaf)
    sibling = SimpleNamespace(hidden=make_ping_node())
    root = SimpleNamespace(child=child, sibling=sibling)

    gateway.ingest(root, path=("root",))

    assert gateway._ingested[id(child)].expanded is False
    assert gateway._ingested[id(sibling)].expanded is False

    assert gateway("root child grandchild ping") == "pong"

    assert gateway._ingested[id(child)].expanded is True
    assert gateway._ingested[id(leaf)].expanded is True
    assert gateway._ingested[id(sibling)].expanded is False


def test_repeated_callable_identity_registers_additional_paths_as_aliases(gateway):
    shared = lambda: "pong"
    first = SimpleNamespace(ping=shared)
    second = SimpleNamespace(ping=shared)

    ingest_python(gateway, first, path=("first",))
    ingest_python(gateway, second, path=("second",))

    first_op = gateway.ops.resolve("first.ping")
    second_op = gateway.ops.resolve("second.ping")

    assert first_op is second_op
    assert gateway("first ping") == "pong"
    assert gateway("second ping") == "pong"
