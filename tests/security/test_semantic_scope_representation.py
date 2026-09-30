from gway.security import semantics
from gway.security.scopes import Scope, ScopeRegistry
from gway.security.tokens import TokenRegistry


def _scope(name, *terms, operations=()):
    return Scope(
        name,
        frozenset(operations),
        frozenset(),
        None,
        frozenset(terms),
    )


def test_semantic_resolution_prefers_existing_exact_scope():
    scopes = (
        _scope("odoo-read", "odoo", "read"),
        _scope("cards-read", "cards", "read"),
        _scope(
            "odoo-cards-read",
            "odoo",
            "cards",
            "read",
            operations={"odoo.cards.list"},
        ),
    )

    resolved = semantics.resolve(scopes, ("cards", "odoo", "read"))

    assert resolved.exact_scopes == ("odoo-cards-read",)
    assert resolved.conjunction == ()
    assert resolved.scopes == ("odoo-cards-read",)
    assert resolved.operations == frozenset({"odoo.cards.list"})


def test_semantic_resolution_falls_back_to_and_decomposition():
    scopes = (
        _scope("odoo-read", "odoo", "read"),
        _scope("cards-read", "cards", "read"),
        _scope(
            "odoo-sales-read",
            "odoo",
            "sales",
            "read",
            operations={"odoo.sales.list"},
        ),
        _scope(
            "odoo-cards-detail-read",
            "odoo",
            "cards",
            "detail",
            "read",
            operations={"odoo.cards.detail"},
        ),
    )

    resolved = semantics.resolve(scopes, ("odoo", "cards", "read"))

    assert resolved.exact_scopes == ()
    assert resolved.conjunction == ("cards-read", "odoo-read")
    assert resolved.scopes == ("odoo-cards-detail-read",)
    assert resolved.operations == frozenset({"odoo.cards.detail"})


def test_conjunctive_representation_never_becomes_or_authority(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    scopes.replace(
        "odoo-read",
        operations={"odoo.sales.list"},
        semantic_terms={"odoo", "read"},
    )
    scopes.replace(
        "cards-read",
        operations={"arthexis.cards.list"},
        semantic_terms={"cards", "read"},
    )
    scopes.replace(
        "odoo-cards-detail-read",
        operations={"odoo.cards.detail"},
        semantic_terms={"odoo", "cards", "detail", "read"},
    )
    tokens = TokenRegistry(path)
    issued = tokens.create(
        "client",
        union_scopes={("odoo", "cards", "read")},
    )

    resolution = semantics.resolve(scopes.all(), ("odoo", "cards", "read"))
    authority = tokens.authenticate(issued.bearer).authority

    assert resolution.conjunction == ("cards-read", "odoo-read")
    assert authority.operations == frozenset({"odoo.cards.detail"})
    assert "odoo.sales.list" not in authority.operations
    assert "arthexis.cards.list" not in authority.operations
