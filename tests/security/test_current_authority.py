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


def _curated_runtime(gateway, tmp_path):
    path = tmp_path / "security.sqlite"
    gateway.security_path = path
    calls = []

    def observe(*, mutate=False):
        return {"kind": "observe", "mutate": mutate}

    def change():
        calls.append("change")
        return {"kind": "change"}

    gateway.observe = gateway.wrap("demo.observe", observe)
    gateway.change = gateway.wrap("demo.change", change)
    gateway.other = gateway.wrap("demo.other", lambda: "other")

    scopes = ScopeRegistry(path)
    scopes.replace("observer", operations={"demo.observe"})
    scopes.replace("operator", operations={"demo.change"})
    scopes.replace("other", operations={"demo.other"})
    return path, scopes, TokenRegistry(path), calls


def test_native_bearer_authority_is_exact_union_of_bound_bundles(gateway, tmp_path):
    _path, _scopes, tokens, calls = _curated_runtime(gateway, tmp_path)
    issued = tokens.create("client", scopes={"observer", "operator"})

    assert gateway.execute_authenticated(
        issued.bearer,
        "observe",
        mutate=False,
    ) == {"kind": "observe", "mutate": False}
    assert gateway.execute_authenticated(issued.bearer, "change") == {
        "kind": "change"
    }
    assert calls == ["change"]

    with pytest.raises(AuthorizationError, match="demo.other"):
        gateway.execute_authenticated(issued.bearer, "other")


def test_read_only_execution_blocks_authorized_mutator_before_side_effect(
    gateway,
    tmp_path,
):
    _path, _scopes, tokens, calls = _curated_runtime(gateway, tmp_path)
    issued = tokens.create("client", scopes={"operator"})

    with pytest.raises(Exception, match="does not support non-mutating execution"):
        gateway.execute_authenticated(issued.bearer, "change", mutate=False)

    assert calls == []


def test_oauth_grant_cannot_regain_parent_bearer_scope_it_did_not_receive(
    gateway,
    tmp_path,
):
    path, _scopes, tokens, calls = _curated_runtime(gateway, tmp_path)
    oauth = OAuthRegistry(path)
    tokens.create("parent", scopes={"observer", "operator"})
    oauth.link("chatgpt", "parent")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"observer"},
        resource=RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)

    assert gateway.execute_authenticated(
        issued.access_token,
        "observe",
        resource=RESOURCE,
        mutate=False,
    )["kind"] == "observe"

    with pytest.raises(AuthorizationError, match="demo.change"):
        gateway.execute_authenticated(
            issued.access_token,
            "change",
            resource=RESOURCE,
        )
    assert calls == []


def test_oauth_authority_shrinks_live_when_parent_bearer_is_narrowed(
    gateway,
    tmp_path,
):
    path, _scopes, tokens, calls = _curated_runtime(gateway, tmp_path)
    oauth = OAuthRegistry(path)
    tokens.create("parent", scopes={"observer", "operator"})
    oauth.link("chatgpt", "parent")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"observer", "operator"},
        resource=RESOURCE,
    )
    issued = oauth.issue_tokens(grant.id)

    assert gateway.execute_authenticated(
        issued.access_token,
        "change",
        resource=RESOURCE,
    ) == {"kind": "change"}
    assert calls == ["change"]

    tokens.replace_scopes("parent", {"observer"})

    assert gateway.execute_authenticated(
        issued.access_token,
        "observe",
        resource=RESOURCE,
        mutate=False,
    )["kind"] == "observe"
    with pytest.raises(AuthorizationError, match="demo.change"):
        gateway.execute_authenticated(
            issued.access_token,
            "change",
            resource=RESOURCE,
        )
    assert calls == ["change"]
