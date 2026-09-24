import base64
import hashlib

import pytest

from gway.remote.account import RemoteAccountApplication
from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.oauth import OAuthProtocolError, RemoteOAuthProtocol
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


MCP_RESOURCE = "https://remote.example.test/mcp"
REDIRECT_URI = "https://chatgpt.com/callback"


def _challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _protocol(tmp_path, *, method):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("logs", operations={"help"})
    tokens.create("operator", scopes={"logs"})
    oauth.link("mcp", "operator")
    issued_client = oauth.create_client(
        "mcp-confidential-client",
        redirect_uris={REDIRECT_URI},
        confidential=True,
        token_endpoint_auth_method=method,
    )
    grant = oauth.create_grant(
        "mcp",
        issued_client.client.client_id,
        scopes={"logs"},
        resource=MCP_RESOURCE,
    )
    account = RemoteAccountApplication(oauth=oauth, tokens=tokens)
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    protocol = RemoteOAuthProtocol(metadata, account)
    return oauth, protocol, issued_client, grant


def _code(oauth, grant):
    verifier = "v" * 64
    issued = oauth.issue_authorization_code(
        grant.id,
        redirect_uri=REDIRECT_URI,
        code_challenge=_challenge(verifier),
    )
    return issued.code, verifier


def _code_params(client_id, code, verifier):
    return {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "resource": MCP_RESOURCE,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }


def test_client_secret_post_authenticates_code_and_refresh(tmp_path):
    oauth, protocol, client, grant = _protocol(
        tmp_path,
        method="client_secret_post",
    )
    code, verifier = _code(oauth, grant)
    params = _code_params(client.client.client_id, code, verifier)
    params["client_secret"] = client.client_secret

    first = protocol.token(params)

    assert first["resource"] == MCP_RESOURCE
    refresh = {
        "grant_type": "refresh_token",
        "client_id": client.client.client_id,
        "client_secret": client.client_secret,
        "resource": MCP_RESOURCE,
        "refresh_token": first["refresh_token"],
    }
    second = protocol.token(refresh)

    assert second["access_token"].startswith("gwa_")


def test_confidential_client_rejects_missing_or_wrong_secret(tmp_path):
    oauth, protocol, client, grant = _protocol(
        tmp_path,
        method="client_secret_post",
    )

    for secret in (None, "wrong"):
        code, verifier = _code(oauth, grant)
        params = _code_params(client.client.client_id, code, verifier)
        if secret is not None:
            params["client_secret"] = secret

        with pytest.raises(OAuthProtocolError) as captured:
            protocol.token(params)

        assert captured.value.error == "invalid_client"
        assert captured.value.status == 401


def test_client_secret_basic_authenticates_without_form_client_id(tmp_path):
    oauth, protocol, client, grant = _protocol(
        tmp_path,
        method="client_secret_basic",
    )
    code, verifier = _code(oauth, grant)
    params = _code_params(client.client.client_id, code, verifier)
    params.pop("client_id")
    raw = f"{client.client.client_id}:{client.client_secret}".encode()
    credential = base64.b64encode(raw).decode()

    payload = protocol.token(
        params,
        headers={"authorization": f"Basic {credential}"},
    )

    assert payload["access_token"].startswith("gwa_")
    assert payload["resource"] == MCP_RESOURCE


def test_public_client_token_exchange_remains_secretless(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("logs", operations={"log.read"})
    tokens.create("operator", scopes={"logs"})
    oauth.link("mcp", "operator")
    client = oauth.create_client(
        "mcp-public-client",
        redirect_uris={REDIRECT_URI},
    )
    grant = oauth.create_grant(
        "mcp",
        client.client_id,
        scopes={"logs"},
        resource="https://remote.example.test/mcp",
    )
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    protocol = RemoteOAuthProtocol(
        metadata,
        RemoteAccountApplication(oauth=oauth, tokens=tokens),
    )
    code, verifier = _code(oauth, grant)
    params = {
        "grant_type": "authorization_code",
        "client_id": client.client_id,
        "resource": metadata.resource,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }

    payload = protocol.token(params)

    assert payload["access_token"].startswith("gwa_")

def test_default_protocol_still_requires_pkce_for_confidential_client(tmp_path):
    _, protocol, client, _ = _protocol(
        tmp_path,
        method="client_secret_post",
    )
    session = protocol.account.new_session()

    with pytest.raises(OAuthProtocolError) as captured:
        protocol.stage_authorization(
            session,
            {
                "response_type": "code",
                "client_id": client.client.client_id,
                "redirect_uri": REDIRECT_URI,
                "resource": MCP_RESOURCE,
                "scope": "logs",
            },
        )

    assert captured.value.error == "invalid_request"
    assert captured.value.description == "code_challenge is required"
