import pytest

from gway.security.authentication import (
    BearerAuthenticationError,
    authenticate_bearer,
)
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


RESOURCE = "https://remote.example.test/mcp"


def _registries(tmp_path):
    path = tmp_path / "security.sqlite"
    return ScopeRegistry(path), TokenRegistry(path), OAuthRegistry(path)


def test_native_bearer_authentication_returns_current_gway_authority(tmp_path):
    scopes, tokens, _ = _registries(tmp_path)
    scopes.replace("reader", operations={"log.read"})
    issued = tokens.create("native-client", scopes={"reader"})

    identity = authenticate_bearer(
        issued.bearer,
        resource=RESOURCE,
        tokens=tokens,
    )

    assert identity.kind == "gway"
    assert identity.principal == "native-client"
    assert identity.scopes == frozenset({"reader"})
    assert identity.authority.operations == frozenset({"log.read"})


def test_oauth_bearer_requires_exact_resource_and_tracks_live_scope(tmp_path):
    scopes, tokens, oauth = _registries(tmp_path)
    scopes.replace("reader", operations={"log.read"})
    tokens.create("operator", scopes={"reader"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"reader"},
        resource=RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)

    with pytest.raises(BearerAuthenticationError):
        authenticate_bearer(
            issued.access_token,
            resource="https://remote.example.test/api",
            oauth=oauth,
        )

    identity = authenticate_bearer(
        issued.access_token,
        resource=RESOURCE,
        oauth=oauth,
    )
    assert identity.kind == "oauth"
    assert identity.client_id == "chatgpt-client"
    assert identity.authority.operations == frozenset({"log.read"})

    scopes.update_grants("reader", add_operations={"log.tail"})
    refreshed = authenticate_bearer(
        issued.access_token,
        resource=RESOURCE,
        oauth=oauth,
    )
    assert refreshed.authority.operations == frozenset({"log.read", "log.tail"})


@pytest.mark.parametrize("bearer", ["", "unknown", "gwr_not_an_access_token"])
def test_unsupported_bearers_fail_uniformly(tmp_path, bearer):
    with pytest.raises(BearerAuthenticationError, match="Invalid bearer token"):
        authenticate_bearer(bearer, path=tmp_path / "security.sqlite")



def test_bearer_authentication_does_not_modify_security_database(tmp_path):
    scopes, tokens, oauth = _registries(tmp_path)
    scopes.replace("reader", operations={"log.read"})
    native = tokens.create("native-client", scopes={"reader"})
    tokens.create("operator", scopes={"reader"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"reader"},
        resource=RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)
    path = tokens.path
    before = path.read_bytes()

    native_identity = authenticate_bearer(
        native.bearer,
        resource=RESOURCE,
        path=path,
    )
    oauth_identity = authenticate_bearer(
        issued.access_token,
        resource=RESOURCE,
        path=path,
    )

    assert native_identity.authority.operations == frozenset({"log.read"})
    assert oauth_identity.authority.operations == frozenset({"log.read"})
    assert path.read_bytes() == before
