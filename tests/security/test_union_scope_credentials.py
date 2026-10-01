import pytest

from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _registries(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("logs-read", operations={"log.read"}, environment={"LOG_SECRET"})
    scopes.replace(
        "odoo-cards-read",
        operations={"odoo.cards.list"},
        environment={"ODOO_SECRET"},
        semantic_terms={"odoo", "cards", "read"},
    )
    scopes.replace(
        "arthexis-cards-read",
        operations={"arthexis.cards.list"},
        environment={"ARTHEXIS_SECRET"},
        semantic_terms={"arthexis", "cards", "read"},
    )
    scopes.replace(
        "odoo-sales-read",
        operations={"odoo.sales.list"},
        semantic_terms={"odoo", "sales", "read"},
    )
    return scopes, tokens, oauth


def test_token_union_scope_is_live_and_does_not_aggregate_environment(tmp_path):
    scopes, tokens, _ = _registries(tmp_path)
    issued = tokens.create(
        "operator",
        scopes={"logs-read"},
        union_scopes={("cards", "read")},
    )

    identity = tokens.authenticate(issued.bearer)
    assert identity.token.scopes == frozenset({"logs-read"})
    assert identity.token.union_scopes == frozenset({("cards", "read")})
    assert identity.authority.operations == frozenset(
        {"log.read", "odoo.cards.list", "arthexis.cards.list"}
    )
    assert identity.authority.environment == frozenset({"LOG_SECRET"})

    scopes.replace(
        "future-cards-read",
        operations={"future.cards.list"},
        semantic_terms={"future", "cards", "read"},
    )
    assert "future.cards.list" in tokens.authenticate(issued.bearer).authority.operations


def test_oauth_union_grant_can_be_narrower_than_linked_token_union(tmp_path):
    _, tokens, oauth = _registries(tmp_path)
    tokens.create("operator", union_scopes={("read",)})
    oauth.link("chatgpt", "operator")

    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes=(),
        union_scopes={("cards", "read")},
    )
    assert grant.union_scopes == frozenset({("cards", "read")})

    issued = oauth.issue_tokens(grant.id)
    authenticated = oauth.authenticate_access(issued.access_token)
    assert authenticated.authority.operations == frozenset(
        {"odoo.cards.list", "arthexis.cards.list"}
    )
    assert authenticated.authority.environment == frozenset()


def test_oauth_union_grant_cannot_exceed_linked_token_union(tmp_path):
    _, tokens, oauth = _registries(tmp_path)
    tokens.create("operator", union_scopes={("cards", "read")})
    oauth.link("chatgpt", "operator")

    with pytest.raises(ValueError, match="exceeds linked token union scopes"):
        oauth.create_grant(
            "chatgpt",
            "chatgpt-client",
            scopes=(),
            union_scopes={("read",)},
        )


def test_oauth_union_authority_shrinks_when_linked_token_union_is_removed(tmp_path):
    _, tokens, oauth = _registries(tmp_path)
    tokens.create("operator", union_scopes={("read",)})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes=(),
        union_scopes={("cards", "read")},
    )
    issued = oauth.issue_tokens(grant.id)
    assert oauth.authenticate_access(issued.access_token).authority.operations

    tokens.replace_union_scopes("operator", ())
    authenticated = oauth.authenticate_access(issued.access_token)
    assert authenticated.grant.union_scopes == frozenset({("cards", "read")})
    assert authenticated.authority.operations == frozenset()


def test_exact_and_union_grants_compose_without_environment_leakage(tmp_path):
    _, tokens, oauth = _registries(tmp_path)
    tokens.create(
        "operator",
        scopes={"logs-read"},
        union_scopes={("cards", "read")},
    )
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"logs-read"},
        union_scopes={("cards", "read")},
    )
    issued = oauth.issue_tokens(grant.id)
    authority = oauth.authenticate_access(issued.access_token).authority
    assert authority.operations == frozenset(
        {"log.read", "odoo.cards.list", "arthexis.cards.list"}
    )
    assert authority.environment == frozenset({"LOG_SECRET"})
