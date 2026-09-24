import base64
from datetime import datetime, timezone
import hashlib
import http.client
import re
import sqlite3
import threading
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from gway.remote.account import RemoteAccountApplication
from gway.remote.oauth import OAuthClientResolver
from gway.remote.server import build_server
from gway.remote.session import RemoteSessionStore
from gway.security.oauth import OAuthAuthenticationError, OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


pytestmark = pytest.mark.main


CLIENT_ID = "chatgpt-client"
REDIRECT_URI = "https://client.example/callback"
RESOURCE = "http://127.0.0.1:9000/mcp"


def _challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _csrf(html):
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _cookie(value):
    return value.split(";", 1)[0]


def _setup(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("chatgpt-logs", operations={"log.read"})
    issued = tokens.create("operator", scopes={"chatgpt-logs"})
    oauth.create_client(CLIENT_ID, redirect_uris={REDIRECT_URI})
    account = RemoteAccountApplication(
        oauth=oauth,
        tokens=tokens,
        sessions=RemoteSessionStore(lifetime_seconds=300),
    )
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="http://127.0.0.1:9000",
        allow_insecure_loopback=True,
        account=account,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=2)
    return scopes, tokens, oauth, issued, server, thread, connection


def _authorization_code(connection, issued_bearer, *, verifier="v" * 64):
    query = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": "chatgpt-logs",
            "resource": RESOURCE,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "state-123",
        }
    )
    connection.request("GET", f"/oauth/authorize?{query}")
    response = connection.getresponse()
    assert response.status == 303
    first_cookie = _cookie(response.getheader("Set-Cookie"))
    assert response.getheader("Location") == "/connect"
    response.read()

    connection.request("GET", "/connect", headers={"Cookie": first_cookie})
    response = connection.getresponse()
    connect_csrf = _csrf(response.read().decode())
    form = urlencode({"csrf": connect_csrf, "bearer": issued_bearer})
    connection.request(
        "POST",
        "/connect",
        body=form,
        headers={
            "Cookie": first_cookie,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    response = connection.getresponse()
    assert response.status == 303
    second_cookie = _cookie(response.getheader("Set-Cookie"))
    assert response.getheader("Location") == "/consent"
    response.read()

    connection.request("GET", "/consent", headers={"Cookie": second_cookie})
    response = connection.getresponse()
    consent_csrf = _csrf(response.read().decode())
    form = urlencode({"csrf": consent_csrf, "decision": "approve"})
    connection.request(
        "POST",
        "/consent",
        body=form,
        headers={
            "Cookie": second_cookie,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    response = connection.getresponse()
    assert response.status == 303
    callback = response.getheader("Location")
    response.read()

    parsed = urlsplit(callback)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == REDIRECT_URI
    params = parse_qs(parsed.query)
    assert params["state"] == ["state-123"]
    assert params["iss"] == ["http://127.0.0.1:9000"]
    return params["code"][0], verifier


def _token(connection, **values):
    form = urlencode(values)
    connection.request(
        "POST",
        "/oauth/token",
        body=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response = connection.getresponse()
    import json

    payload = json.loads(response.read().decode())
    return response.status, payload


def test_http_authorization_code_pkce_exchange_and_single_use(tmp_path):
    _, _, _, issued, server, thread, connection = _setup(tmp_path)
    try:
        code, verifier = _authorization_code(connection, issued.bearer)
        status, payload = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier=verifier,
        )
        assert status == 200
        assert payload["token_type"] == "Bearer"
        assert payload["scope"] == "chatgpt-logs"
        assert payload["resource"] == RESOURCE
        assert payload["access_token"].startswith("gwa_")
        assert payload["refresh_token"].startswith("gwr_")

        status, payload = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier=verifier,
        )
        assert status == 400
        assert payload["error"] == "invalid_grant"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_token_rejects_bad_verifier_and_expired_code(tmp_path):
    _, _, oauth, issued, server, thread, connection = _setup(tmp_path)
    try:
        code, verifier = _authorization_code(connection, issued.bearer)
        status, payload = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier="wrong" * 16,
        )
        assert status == 400
        assert payload["error"] == "invalid_grant"

        code_hash = hashlib.sha256(code.encode()).hexdigest()
        with sqlite3.connect(oauth.path) as database:
            database.execute(
                "UPDATE oauth_authorization_codes SET expires_at = ? WHERE code_hash = ?",
                (datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(), code_hash),
            )
        status, payload = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier=verifier,
        )
        assert status == 400
        assert payload["error"] == "invalid_grant"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_authorize_requires_exact_registered_redirect(tmp_path):
    _, _, _, _, server, thread, connection = _setup(tmp_path)
    try:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": "https://evil.example/callback",
                "scope": "chatgpt-logs",
                "resource": RESOURCE,
                "code_challenge": _challenge("v" * 64),
                "code_challenge_method": "S256",
            }
        )
        connection.request("GET", f"/oauth/authorize?{query}")
        response = connection.getresponse()
        import json

        payload = json.loads(response.read().decode())
        assert response.status == 400
        assert payload["error"] == "invalid_request"
        assert response.getheader("Location") is None
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_refresh_tracks_live_scope_policy_and_rejects_scope_change(tmp_path):
    scopes, _, oauth, issued, server, thread, connection = _setup(tmp_path)
    try:
        code, verifier = _authorization_code(connection, issued.bearer)
        status, first = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier=verifier,
        )
        assert status == 200

        status, payload = _token(
            connection,
            grant_type="refresh_token",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            refresh_token=first["refresh_token"],
            scope="admin",
        )
        assert status == 400
        assert payload["error"] == "invalid_scope"

        scopes.replace("chatgpt-logs", operations={"log.read", "log.tail"})
        status, refreshed = _token(
            connection,
            grant_type="refresh_token",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            refresh_token=first["refresh_token"],
        )
        assert status == 200
        authority = oauth.authenticate_access(refreshed["access_token"]).authority
        assert authority.operations == frozenset({"log.read", "log.tail"})
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_revocation_invalidates_access_token(tmp_path):
    _, _, oauth, issued, server, thread, connection = _setup(tmp_path)
    try:
        code, verifier = _authorization_code(connection, issued.bearer)
        _, payload = _token(
            connection,
            grant_type="authorization_code",
            client_id=CLIENT_ID,
            resource=RESOURCE,
            code=code,
            redirect_uri=REDIRECT_URI,
            code_verifier=verifier,
        )
        form = urlencode({"token": payload["access_token"]})
        connection.request(
            "POST",
            "/oauth/revoke",
            body=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        assert response.status == 200
        response.read()

        with pytest.raises(OAuthAuthenticationError):
            oauth.authenticate_access(payload["access_token"])
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cimd_resolver_accepts_public_client_metadata_without_registration(tmp_path):
    oauth = OAuthRegistry(tmp_path / "security.sqlite")
    client_id = "https://chatgpt.example/oauth/client.json"
    resolver = OAuthClientResolver(
        oauth,
        fetcher=lambda url: {
            "client_id": url,
            "redirect_uris": ["https://chatgpt.example/callback"],
            "token_endpoint_auth_methods": ["none"],
        },
    )

    client = resolver.resolve(client_id)

    assert client.client_id == client_id
    assert client.redirect_uris == frozenset({"https://chatgpt.example/callback"})
