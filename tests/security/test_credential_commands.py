from gway.security.oauth import OAuthAuthenticationError, OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry

import pytest


def _oauth_state(gateway, tmp_path):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.create("logs")
    tokens.create("operator", scopes={"logs"})
    oauth.create_client(
        "chatgpt-client",
        redirect_uris={"https://chatgpt.com/callback"},
    )
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"logs"},
        resource="https://remote.example/mcp",
    )
    issued = oauth.issue_tokens(grant.id)
    return path, tokens, oauth, grant, issued


def test_plural_namespace_defaults_to_singular_list(gateway, tmp_path):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    scopes = ScopeRegistry(path)
    scopes.create("logs")
    TokenRegistry(path).create("reader", scopes={"logs"})

    listed = gateway("security tokens")
    explicit = gateway("security token list")
    singular = gateway("security token")

    assert listed == explicit
    assert [token.name for token in listed] == ["reader"]
    assert singular["group"] == "security token"
    assert any(item["name"] == "list" for item in singular["operations"])


def test_explicit_plural_operation_beats_plural_list_fallback(gateway):
    gateway.wrap("widget.list", lambda: ["listed"])
    gateway.wrap("widgets", lambda: "explicit")

    assert gateway("widgets") == "explicit"


def test_oauth_plural_commands_expose_safe_inspection(gateway, tmp_path):
    _, _, oauth, grant, issued = _oauth_state(gateway, tmp_path)

    grants = gateway("security oauth grants")
    tokens = gateway("security oauth tokens")

    assert grants == [grant]
    assert {token.kind for token in tokens} == {"access", "refresh"}
    assert {token.grant_id for token in tokens} == {grant.id}
    assert issued.access_token not in repr(tokens)
    assert issued.refresh_token not in repr(tokens)

    access = next(token for token in tokens if token.kind == "access")
    shown = gateway(f"security oauth token show {access.public_id}")
    assert shown == access


def test_oauth_grant_bind_updates_live_access_authority(gateway, tmp_path):
    path, tokens, oauth, grant, issued = _oauth_state(gateway, tmp_path)
    scopes = ScopeRegistry(path)
    scopes.replace("operator-read", operations={"watch", "wire.check"})
    tokens.bind("operator", "operator-read")

    updated = gateway(
        f"security oauth grant bind {grant.id} operator-read"
    )

    assert updated.scopes == frozenset({"logs", "operator-read"})
    assert oauth.authenticate_access(issued.access_token).authority.operations == frozenset(
        {"watch", "wire.check"}
    )


def test_oauth_token_clear_revokes_credentials_but_preserves_grant(gateway, tmp_path):
    _, _, oauth, grant, issued = _oauth_state(gateway, tmp_path)

    assert gateway("security oauth token clear") == 2
    assert oauth.get_grant(grant.id).revoked_at is None
    assert oauth.get_link("chatgpt").revoked_at is None

    with pytest.raises(OAuthAuthenticationError):
        oauth.authenticate_access(issued.access_token)
    with pytest.raises(OAuthAuthenticationError):
        oauth.rotate_refresh(issued.refresh_token)


def test_security_token_clear_cascades_oauth_state_but_preserves_client(
    gateway, tmp_path
):
    _, tokens, oauth, _, _ = _oauth_state(gateway, tmp_path)

    assert gateway("security token clear") == 1
    assert tokens.all() == []
    assert oauth.links() == []
    assert oauth.grants() == []
    assert oauth.credentials() == []
    assert oauth.require_client("chatgpt-client").client_id == "chatgpt-client"
