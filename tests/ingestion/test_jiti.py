import pathlib
from types import SimpleNamespace


def test_jiti_expands_only_requested_branch(gateway, make_ping_node):
    child = SimpleNamespace(grandchild=make_ping_node())
    sibling = SimpleNamespace(hidden=make_ping_node())
    root = SimpleNamespace(child=child, sibling=sibling)

    gateway.ingest(root, path=("root",))

    assert gateway.ops.resolve("root.child.grandchild.ping") is None
    assert gateway("root child grandchild ping") == "pong"
    assert gateway.ops.resolve("root.sibling.hidden.ping") is None


def test_jiti_works_with_dotted_command_path(gateway, make_ping_node):
    child = SimpleNamespace(leaf=make_ping_node())
    root = SimpleNamespace(child=child)
    gateway.ingest(root, path=("root",))

    assert gateway("root.child.leaf.ping") == "pong"


def test_jiti_reuses_expanded_branch(gateway, make_ping_node):
    child = make_ping_node()
    root = SimpleNamespace(child=child)
    gateway.ingest(root, path=("root",))

    assert gateway("root child ping") == "pong"
    assert gateway("root child ping") == "pong"


def test_stdlib_pathlib_can_jit_expand_class_branch(gateway):
    gateway.ingest(pathlib)

    assert gateway.ops.resolve("pathlib.Path.cwd") is None

    result = gateway("pathlib Path cwd")

    assert isinstance(result, pathlib.Path)
    assert gateway.ops.resolve("pathlib.Path.cwd") is not None
