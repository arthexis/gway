import base64
import hashlib

import pytest

from gway.remote.account import RemoteAccountApplication
from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.oauth import OAuthProtocolError, RemoteOAuthProtocol
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


ACTIONS_RESOURCE = "https://remote.example.test/actions"
REDIRECT_URI = "https://chatgpt.com/callback"


def _challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _protocol(tmp_path, *, method):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("chatgpt-actions", operations={"help"})
    tokens.create("operator", scopes={"chatgpt-actions"})
    oauth.link("chatgpt", "operator")
    issued_client = oauth.create_client(
        "chatgpt-actions-client",
        redirect_uris={REDIRECT_URI},
        confidential=True,
        token_endpoint_auth_method=method,
    )
    grant = oauth.create_grant(
        "chatgpt",
        issued_client.client.client_id,
        scopes={"chatgpt-actions"},
        resource=ACTIONS_RESOURCE,
    )
    account = RemoteAccountApplication(oauth=oauth, tokens=tokens)
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/actions",
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
        "resource": ACTIONS_RESOURCE,
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

    assert first["resource"] == ACTIONS_RESOURCE
    refresh = {
        "grant_type": "refresh_token",
        "client_id": client.client.client_id,
        "client_secret": client.client_secret,
        "resource": ACTIONS_RESOURCE,
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
    assert payload["resource"] == ACTIONS_RESOURCE


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


def test_actions_confidential_client_can_authorize_and_exchange_without_pkce(tmp_path):
    oauth, _, client, grant = _protocol(
        tmp_path,
        method="client_secret_post",
    )
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/actions",
    )
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=TokenRegistry(oauth.path),
    )
    protocol = RemoteOAuthProtocol(
        metadata,
        account,
        allow_confidential_without_pkce=True,
    )
    session = account.new_session()

    protocol.stage_authorization(
        session,
        {
            "response_type": "code",
            "client_id": client.client.client_id,
            "redirect_uri": REDIRECT_URI,
            "resource": ACTIONS_RESOURCE,
            "scope": "chatgpt-actions",
            "state": "opaque-state",
        },
    )

    assert session.pending_code_challenge == ""
    redirect = protocol.finish_authorization(session, grant)
    from urllib.parse import parse_qs, urlsplit

    code = parse_qs(urlsplit(redirect).query)["code"][0]
    payload = protocol.token(
        {
            "grant_type": "authorization_code",
            "client_id": client.client.client_id,
            "client_secret": client.client_secret,
            "resource": ACTIONS_RESOURCE,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
    )

    assert payload["access_token"].startswith("gwa_")
    assert payload["resource"] == ACTIONS_RESOURCE


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
                "resource": ACTIONS_RESOURCE,
                "scope": "chatgpt-actions",
            },
        )

    assert captured.value.error == "invalid_request"
    assert captured.value.description == "code_challenge is required"


def test_actions_compatibility_still_requires_pkce_for_public_client(tmp_path):
    path = tmp_path / "public.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("chatgpt-actions", operations={"help"})
    tokens.create("operator", scopes={"chatgpt-actions"})
    oauth.link("chatgpt", "operator")
    client = oauth.create_client(
        "public-actions-client",
        redirect_uris={REDIRECT_URI},
    )
    account = RemoteAccountApplication(oauth=oauth, tokens=tokens)
    protocol = RemoteOAuthProtocol(
        RemoteOAuthMetadata.from_origin(
            "https://remote.example.test",
            resource_path="/actions",
        ),
        account,
        allow_confidential_without_pkce=True,
    )

    with pytest.raises(OAuthProtocolError) as captured:
        protocol.stage_authorization(
            account.new_session(),
            {
                "response_type": "code",
                "client_id": client.client_id,
                "redirect_uri": REDIRECT_URI,
                "resource": ACTIONS_RESOURCE,
                "scope": "chatgpt-actions",
            },
        )

    assert captured.value.description == "code_challenge is required"


