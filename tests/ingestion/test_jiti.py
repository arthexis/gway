from types import SimpleNamespace
import pathlib


def test_jiti_expands_only_requested_branch(gateway):
    class Leaf:
        def ping(self):
            return "pong"

    leaf = Leaf()
    child = SimpleNamespace(grandchild=leaf)
    sibling = SimpleNamespace(hidden=Leaf())
    root = SimpleNamespace(child=child, sibling=sibling)

    gateway.ingest(root, path=("root",))

    assert gateway.ops.resolve("root.child.grandchild.ping") is None
    assert gateway._ingested[id(child)].expanded is False
    assert gateway._ingested[id(sibling)].expanded is False

    assert gateway("root child grandchild ping") == "pong"

    assert gateway._ingested[id(child)].expanded is True
    assert gateway._ingested[id(leaf)].expanded is True
    assert gateway._ingested[id(sibling)].expanded is False
    assert gateway.ops.resolve("root.sibling.hidden.ping") is None


def test_jiti_works_with_dotted_command_path(gateway):
    class Leaf:
        def ping(self):
            return "pong"

    child = SimpleNamespace(leaf=Leaf())
    root = SimpleNamespace(child=child)
    gateway.ingest(root, path=("root",))

    assert gateway("root.child.leaf.ping") == "pong"


def test_jiti_does_not_reexpand_already_expanded_objects(gateway):
    class Child:
        def ping(self):
            return "pong"

    child = Child()
    root = SimpleNamespace(child=child)
    gateway.ingest(root, path=("root",))

    assert gateway("root child ping") == "pong"
    record = gateway._ingested[id(child)]
    assert record.expanded is True

    assert gateway("root child ping") == "pong"
    assert record.expanded is True


def test_stdlib_pathlib_can_jit_expand_class_branch(gateway):
    gateway.ingest(pathlib)

    path_record = gateway._ingested[id(pathlib.Path)]
    assert path_record.expanded is False
    assert gateway.ops.resolve("pathlib.Path.cwd") is None

    result = gateway("pathlib Path cwd")

    assert isinstance(result, pathlib.Path)
    assert path_record.expanded is True
