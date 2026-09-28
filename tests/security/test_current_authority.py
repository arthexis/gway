import pytest

from gway.authorization import AuthorizationError
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


RESOURCE = "https://remote.example.test/mcp"


def test_security_whoami_reports_local_unconstrained_execution(gateway):
    assert gateway("security whoami") == {
        "kind": "local",
        "principal": None,
        "client_id": None,
        "scopes": [],
        "constrained": False,
        "operations": None,
        "environment": None,
    }


def test_security_introspection_is_available_to_constrained_caller(gateway):
    with gateway.authorized(
        operations={"log.read"},
        environment={"VISIBLE"},
        kind="oauth",
        principal="chatgpt",
        client_id="chatgpt-client",
        scopes={"logs-read"},
    ):
        assert gateway("security scope current") == {
            "constrained": True,
            "operations": ["log.read"],
            "environment": ["VISIBLE"],
        }
        assert gateway("security whoami")["scopes"] == ["logs-read"]
        with pytest.raises(AuthorizationError, match="security.token.list"):
            gateway("security token list")


def test_native_bearer_can_inspect_own_identity_without_explicit_grant(
    gateway, tmp_path
):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    scopes = ScopeRegistry(path)
    scopes.replace("reader", operations={"log.read"}, environment=())
    issued = TokenRegistry(path).create("native-client", scopes={"reader"})

    result = gateway.execute_authenticated(
        issued.bearer,
        "security whoami",
        mutate=False,
    )

    assert result["kind"] == "gway"
    assert result["principal"] == "native-client"
    assert result["client_id"] == "gway:native-client"
    assert result["scopes"] == ["reader"]
    assert result["operations"] == ["log.read"]


def test_oauth_bearer_can_inspect_own_identity_without_explicit_grant(
    gateway, tmp_path
):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("reader", operations={"log.read"}, environment=())
    tokens.create("operator", scopes={"reader"})
    oauth.link("chatgpt", "operator")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"reader"},
        resource=RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)

    result = gateway.execute_authenticated(
        issued.access_token,
        "security whoami",
        resource=RESOURCE,
        mutate=False,
    )

    assert result["kind"] == "oauth"
    assert result["principal"] == "chatgpt"
    assert result["client_id"] == "chatgpt-client"
    assert result["scopes"] == ["reader"]
    assert result["operations"] == ["log.read"]
