from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _semantic_scopes(path):
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
    return scopes


def test_token_inspection_shows_conjunctive_union_without_broadening(gateway, tmp_path):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    _semantic_scopes(path)
    tokens = TokenRegistry(path)
    tokens.create(
        "client",
        union_scopes={("odoo", "cards", "read")},
    )

    inspected = gateway("security token inspect client")

    assert inspected["exact_scopes"] == []
    assert inspected["matched_scopes"] == ["odoo-cards-detail-read"]
    assert inspected["effective_operations"] == ["odoo.cards.detail"]
    union = inspected["union_scopes"][0]
    assert union["terms"] == ["cards", "odoo", "read"]
    assert union["exact_scopes"] == []
    assert union["conjunction"] == ["cards-read", "odoo-read"]


def test_token_inspection_prefers_existing_exact_semantic_scope(gateway, tmp_path):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    scopes = _semantic_scopes(path)
    scopes.replace(
        "odoo-cards-read",
        operations={"odoo.cards.list"},
        semantic_terms={"odoo", "cards", "read"},
    )
    TokenRegistry(path).create(
        "client",
        union_scopes={("odoo", "cards", "read")},
    )

    union = gateway("security token inspect client")["union_scopes"][0]

    assert union["exact_scopes"] == ["odoo-cards-read"]
    assert union["conjunction"] == []
    assert union["matched_scopes"] == [
        "odoo-cards-detail-read",
        "odoo-cards-read",
    ]


def test_oauth_grant_inspection_marks_union_that_parent_token_no_longer_allows(
    gateway,
    tmp_path,
):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    _semantic_scopes(path)
    tokens = TokenRegistry(path)
    tokens.create(
        "operator",
        union_scopes={("read",)},
    )
    oauth = OAuthRegistry(path)
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "client",
        scopes=(),
        union_scopes={("odoo", "cards", "read")},
    )

    active = gateway(f"security oauth grant inspect {grant.id}")
    assert active["union_scopes"] == [
        {"terms": ["cards", "odoo", "read"], "effective": True}
    ]
    assert active["effective_operations"] == ["odoo.cards.detail"]

    # Narrow the parent token onto a different product-specific card authority.
    # A parent `cards read` grant would still contain the child `odoo cards read`
    # union, so it must remain effective; `arthexis cards read` does not.
    tokens.replace_union_scopes("operator", {("arthexis", "cards", "read")})
    reduced = gateway(f"security oauth grant inspect {grant.id}")

    assert reduced["union_scopes"] == [
        {"terms": ["cards", "odoo", "read"], "effective": False}
    ]
    assert reduced["effective_union_scopes"] == []
    assert reduced["effective_operations"] == []
