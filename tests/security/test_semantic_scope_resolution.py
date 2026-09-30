import pytest

from gway.security.scopes import EffectiveScope, ScopeRegistry
from gway.security.semantics import SemanticResolution


def _semantic_scopes(path):
    registry = ScopeRegistry(path)
    registry.replace(
        "odoo-cards-read",
        operations={"odoo.cards.list", "shared.read"},
        environment={"ODOO_SECRET"},
        semantic_terms={"odoo", "cards", "read"},
    )
    registry.replace(
        "arthexis-cards-read",
        operations={"arthexis.cards.list", "shared.read"},
        environment={"ARTHEXIS_SECRET"},
        semantic_terms={"arthexis", "cards", "read"},
    )
    registry.replace(
        "odoo-sales-read",
        operations={"odoo.sales.list"},
        semantic_terms={"odoo", "sales", "read"},
    )
    registry.replace(
        "legacy-read",
        operations={"legacy.read"},
    )
    return registry


def test_security_scope_contains_uses_explicit_semantic_terms(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    assert gateway("security scope contains odoo-cards-read cards read") is True
    assert gateway("security scope contains odoo-cards-read read cards") is True
    assert gateway("security scope contains odoo-cards-read cards write") is False
    assert gateway("security scope contains legacy-read read") is False


def test_security_scope_match_returns_only_matching_semantic_leaves(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    matches = gateway("security scope match cards read")

    assert [scope.name for scope in matches] == [
        "arthexis-cards-read",
        "odoo-cards-read",
    ]
    assert all(scope.semantic_terms for scope in matches)


def test_security_scope_match_is_order_independent(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    forward = gateway("security scope match odoo read")
    reverse = gateway("security scope match read odoo")

    assert forward == reverse
    assert [scope.name for scope in forward] == [
        "odoo-cards-read",
        "odoo-sales-read",
    ]


def test_security_scope_union_returns_least_broad_common_authority(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    assert gateway(
        "security scope union odoo-cards-read arthexis-cards-read"
    ) == frozenset({"cards", "read"})
    assert gateway(
        "security scope union odoo-cards-read odoo-sales-read"
    ) == frozenset({"odoo", "read"})


def test_security_scope_union_rejects_legacy_or_unbounded_result(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    registry = _semantic_scopes(gateway.security_path)
    registry.replace(
        "arthexis-sales-write",
        operations={"arthexis.sales.write"},
        semantic_terms={"arthexis", "sales", "write"},
    )

    with pytest.raises(ValueError, match="has no semantic terms"):
        gateway("security scope union odoo-cards-read legacy-read")

    with pytest.raises(ValueError, match="no common terms"):
        gateway("security scope union odoo-cards-read arthexis-sales-write")


def test_semantic_resolve_returns_leaf_names_and_operation_union_only(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    resolved = gateway("security scope resolve cards read --semantic")

    assert resolved == SemanticResolution(
        terms=frozenset({"cards", "read"}),
        scopes=("arthexis-cards-read", "odoo-cards-read"),
        operations=frozenset(
            {"arthexis.cards.list", "odoo.cards.list", "shared.read"}
        ),
    )
    assert not hasattr(resolved, "environment")


def test_semantic_resolve_expands_when_a_new_matching_leaf_is_published(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    registry = _semantic_scopes(gateway.security_path)

    before = gateway("security scope resolve cards read --semantic")
    registry.replace(
        "future-cards-read",
        operations={"future.cards.list"},
        semantic_terms={"future", "cards", "read"},
    )
    after = gateway("security scope resolve cards read --semantic")

    assert "future-cards-read" not in before.scopes
    assert "future-cards-read" in after.scopes
    assert "future.cards.list" in after.operations


def test_exact_scope_resolve_remains_exact_by_default(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    resolved = gateway("security scope resolve odoo-cards-read")

    assert resolved == EffectiveScope(
        operations=frozenset({"odoo.cards.list", "shared.read"}),
        environment=frozenset({"ODOO_SECRET"}),
    )
    assert "arthexis.cards.list" not in resolved.operations


def test_semantic_operations_reject_empty_term_requests(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _semantic_scopes(gateway.security_path)

    with pytest.raises(ValueError, match="at least one term"):
        gateway("security scope match")
