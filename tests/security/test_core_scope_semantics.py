from gway.security.defaults import converge_scope_registry
from gway.security.scopes import ScopeRegistry
from gway.security.semantics import resolve


def test_existing_core_scopes_publish_semantic_terms(tmp_path):
    registry = ScopeRegistry(tmp_path / "state.sqlite")
    converge_scope_registry(registry)

    assert registry.require("logs-read").semantic_terms == frozenset({"logs", "read"})
    assert registry.require("source-read").semantic_terms == frozenset({"source", "read"})
    assert registry.require("source-admin").semantic_terms == frozenset({"source", "admin"})
    assert registry.require("operator-read").semantic_terms == frozenset({"operator", "read"})
    assert registry.require("full-access").semantic_terms == frozenset()


def test_real_core_semantic_resolution_uses_existing_scopes_only(tmp_path):
    registry = ScopeRegistry(tmp_path / "state.sqlite")
    converge_scope_registry(registry)
    scopes = registry.all()

    source_read = resolve(scopes, {"source", "read"})
    assert source_read.exact_scopes == ("source-read",)
    assert source_read.scopes == ("source-read",)
    assert "source" in source_read.operations
    assert "github.update_ruleset" not in source_read.operations

    read = resolve(scopes, {"read"})
    assert read.scopes == ("logs-read", "operator-read", "source-read")
    assert "__all__" not in read.operations


def test_full_access_remains_exact_only(tmp_path):
    registry = ScopeRegistry(tmp_path / "state.sqlite")
    converge_scope_registry(registry)

    resolved = resolve(registry.all(), {"read"})

    assert "full-access" not in resolved.scopes
    assert "__all__" not in resolved.operations
