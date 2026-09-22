import base64
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

import pytest

from gway.security.oauth import OAuthAuthenticationError, OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _registries(tmp_path):
    path = tmp_path / "security.sqlite"
    return ScopeRegistry(path), TokenRegistry(path), OAuthRegistry(path)


def _challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _linked_grant(tmp_path):
    scopes, tokens, oauth = _registries(tmp_path)
    scopes.replace("logs", operations={"log.read"})
    scopes.replace("status", operations={"status"})
    tokens.create("operator", scopes={"logs", "status"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant("chatgpt", "chatgpt-client", scopes={"logs"})
    return scopes, tokens, oauth, grant


def test_security_state_migrates_v3_to_v4_without_losing_existing_policy(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace("logs", operations={"log.read"})
    issued = tokens.create("reader", scopes={"logs"})

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 3")

    oauth = OAuthRegistry(path)
    oauth.create_client(
        "chatgpt",
        redirect_uris={"https://chatgpt.com/callback"},
        metadata_url="https://chatgpt.com/client.json",
    )

    assert scopes.require("logs").operations == frozenset({"log.read"})
    assert tokens.require("reader") == issued.token
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "oauth_clients",
        "oauth_links",
        "oauth_grants",
        "oauth_grant_scopes",
        "oauth_authorization_codes",
        "oauth_access_tokens",
        "oauth_refresh_tokens",
    } <= tables


def test_oauth_client_metadata_round_trips(tmp_path):
    _, _, oauth = _registries(tmp_path)

    client = oauth.create_client(
        "chatgpt",
        redirect_uris={
            "https://chatgpt.com/a",
            "https://chatgpt.com/b",
        },
        metadata_url="https://chatgpt.com/client.json",
    )

    assert client.client_id == "chatgpt"
    assert client.redirect_uris == frozenset(
        {"https://chatgpt.com/a", "https://chatgpt.com/b"}
    )
    assert client.metadata_url == "https://chatgpt.com/client.json"
    assert client.disabled is False


def test_oauth_grant_cannot_exceed_linked_gway_token_scopes(tmp_path):
    scopes, tokens, oauth = _registries(tmp_path)
    scopes.create("logs")
    scopes.create("admin")
    tokens.create("operator", scopes={"logs"})
    oauth.link("chatgpt", "operator")

    with pytest.raises(ValueError, match="exceeds linked token scopes"):
        oauth.create_grant(
            "chatgpt",
            "client",
            scopes={"logs", "admin"},
        )


def test_authorization_code_requires_s256_and_is_single_use(tmp_path):
    _, _, oauth, grant = _linked_grant(tmp_path)
    verifier = "v" * 64
    issued = oauth.issue_authorization_code(
        grant.id,
        redirect_uri="https://chatgpt.com/callback",
        code_challenge=_challenge(verifier),
    )

    consumed = oauth.consume_authorization_code(
        issued.code,
        redirect_uri="https://chatgpt.com/callback",
        code_verifier=verifier,
    )

    assert consumed == grant
    with pytest.raises(OAuthAuthenticationError):
        oauth.consume_authorization_code(
            issued.code,
            redirect_uri="https://chatgpt.com/callback",
            code_verifier=verifier,
        )


@pytest.mark.parametrize(
    ("redirect_uri", "verifier"),
    [
        ("https://evil.example/callback", "v" * 64),
        ("https://chatgpt.com/callback", "wrong" * 16),
    ],
)
def test_authorization_code_rejects_redirect_or_pkce_mismatch(
    tmp_path,
    redirect_uri,
    verifier,
):
    _, _, oauth, grant = _linked_grant(tmp_path)
    expected = "v" * 64
    issued = oauth.issue_authorization_code(
        grant.id,
        redirect_uri="https://chatgpt.com/callback",
        code_challenge=_challenge(expected),
    )

    with pytest.raises(OAuthAuthenticationError):
        oauth.consume_authorization_code(
            issued.code,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
        )


def test_access_authority_tracks_live_scope_definition_and_token_bindings(tmp_path):
    scopes, tokens, oauth, grant = _linked_grant(tmp_path)
    issued = oauth.issue_tokens(grant.id)

    authenticated = oauth.authenticate_access(issued.access_token)
    assert authenticated.authority.operations == frozenset({"log.read"})

    scopes.replace("logs", operations={"log.read", "log.tail"})
    authenticated = oauth.authenticate_access(issued.access_token)
    assert authenticated.authority.operations == frozenset({"log.read", "log.tail"})

    tokens.unbind("operator", "logs")
    authenticated = oauth.authenticate_access(issued.access_token)
    assert authenticated.authority.operations == frozenset()


def test_revoked_link_or_grant_invalidates_access_token(tmp_path):
    _, _, oauth, grant = _linked_grant(tmp_path)
    first = oauth.issue_tokens(grant.id)
    oauth.revoke_grant(grant.id)

    with pytest.raises(OAuthAuthenticationError):
        oauth.authenticate_access(first.access_token)

    _, _, oauth2, grant2 = _linked_grant(tmp_path / "second")
    second = oauth2.issue_tokens(grant2.id)
    oauth2.revoke_link("chatgpt")

    with pytest.raises(OAuthAuthenticationError):
        oauth2.authenticate_access(second.access_token)


def test_disabled_or_expired_linked_gway_token_invalidates_oauth(tmp_path):
    _, tokens, oauth, grant = _linked_grant(tmp_path)
    issued = oauth.issue_tokens(grant.id)

    tokens.disable("operator")
    with pytest.raises(OAuthAuthenticationError):
        oauth.authenticate_access(issued.access_token)

    scopes2, tokens2, oauth2 = _registries(tmp_path / "expired")
    scopes2.create("logs")
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    tokens2.create("operator", scopes={"logs"}, expires_at=expired)
    oauth2.link("chatgpt", "operator")
    grant2 = oauth2.create_grant("chatgpt", "client", scopes={"logs"})

    with pytest.raises(OAuthAuthenticationError):
        oauth2.issue_tokens(grant2.id)


def test_refresh_rotation_is_one_time_and_cannot_restore_removed_scope(tmp_path):
    _, tokens, oauth, grant = _linked_grant(tmp_path)
    issued = oauth.issue_tokens(grant.id)
    tokens.unbind("operator", "logs")

    rotated = oauth.rotate_refresh(issued.refresh_token)

    assert oauth.authenticate_access(rotated.access_token).authority.operations == frozenset()
    with pytest.raises(OAuthAuthenticationError):
        oauth.rotate_refresh(issued.refresh_token)


def test_access_and_refresh_revocation(tmp_path):
    _, _, oauth, grant = _linked_grant(tmp_path)
    issued = oauth.issue_tokens(grant.id)

    assert oauth.revoke(issued.access_token) is True
    with pytest.raises(OAuthAuthenticationError):
        oauth.authenticate_access(issued.access_token)

    assert oauth.revoke(issued.refresh_token) is True
    with pytest.raises(OAuthAuthenticationError):
        oauth.rotate_refresh(issued.refresh_token)


def test_oauth_plaintext_credentials_are_never_persisted(tmp_path):
    _, _, oauth, grant = _linked_grant(tmp_path)
    verifier = "v" * 64
    code = oauth.issue_authorization_code(
        grant.id,
        redirect_uri="https://chatgpt.com/callback",
        code_challenge=_challenge(verifier),
    )
    issued = oauth.issue_tokens(grant.id)

    with sqlite3.connect(oauth.path) as connection:
        dump = "\n".join(connection.iterdump())

    assert code.code not in dump
    assert issued.access_token not in dump
    assert issued.refresh_token not in dump
