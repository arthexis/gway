import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.server import RemoteApplication, RemoteDiscoveryApplication, build_server


def test_discovery_application_routes_canonical_well_known_paths():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteDiscoveryApplication(metadata)

    status, headers, protected = app.response(
        "GET",
        "/.well-known/oauth-protected-resource/mcp",
    )
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert protected["resource"] == "https://remote.example.test/mcp"

    status, _, authorization = app.response(
        "GET",
        "/.well-known/oauth-authorization-server",
    )
    assert status == 200
    assert authorization["issuer"] == "https://remote.example.test"

    status, _, client = app.response(
        "GET",
        "/.well-known/gway-acceptance-client",
    )
    assert status == 200
    assert client == {
        "client_id": "https://remote.example.test/.well-known/gway-acceptance-client",
        "redirect_uris": ["http://127.0.0.1:8765/callback"],
        "token_endpoint_auth_methods": ["none"],
    }


def test_discovery_application_reserves_advertised_oauth_routes():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteDiscoveryApplication(metadata)

    for path in ("/oauth/authorize", "/oauth/token", "/oauth/revoke"):
        status, _, payload = app.response("GET", path)
        assert status == 501
        assert payload == {"error": "not_implemented"}


def test_discovery_application_rejects_writes_and_unknown_paths():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteDiscoveryApplication(metadata)

    status, headers, payload = app.response(
        "POST",
        "/.well-known/oauth-authorization-server",
    )
    assert status == 405
    assert headers["allow"] == "GET"
    assert payload == {"error": "method_not_allowed"}

    status, _, payload = app.response("GET", "/missing")
    assert status == 404
    assert payload == {"error": "not_found"}


def test_real_loopback_http_serves_both_discovery_documents():
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="http://127.0.0.1:9000",
        allow_insecure_loopback=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        with urlopen(
            f"http://{host}:{port}/.well-known/oauth-protected-resource/mcp",
            timeout=2,
        ) as response:
            protected = json.load(response)
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/json"

        with urlopen(
            f"http://{host}:{port}/.well-known/oauth-authorization-server",
            timeout=2,
        ) as response:
            authorization = json.load(response)
            assert response.status == 200

        assert protected["resource"] == "http://127.0.0.1:9000/mcp"
        assert protected["authorization_servers"] == ["http://127.0.0.1:9000"]
        assert authorization["issuer"] == "http://127.0.0.1:9000"
        assert authorization["protected_resources"] == ["http://127.0.0.1:9000/mcp"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_http_rejects_non_get_discovery_request():
    server = build_server(
        "127.0.0.1",
        0,
        public_origin="http://localhost:9000",
        allow_insecure_loopback=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        request = Request(
            f"http://{host}:{port}/.well-known/oauth-authorization-server",
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
        except HTTPError as error:
            assert error.code == 405
            assert error.headers["Allow"] == "GET"
            assert json.load(error) == {"error": "method_not_allowed"}
        else:
            raise AssertionError("POST discovery request unexpectedly succeeded")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def test_remote_privacy_page_is_public_and_describes_remote_data():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteApplication(metadata)

    status, headers, body = app.response("GET", "/privacy")

    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert "G-Way Remote Privacy Policy" in body
    assert "connected MCP clients" in body
    assert "OAuth client identifiers" in body
    assert "G-Way command strings" in body
    assert "does not sell personal data" in body

    status, headers, payload = app.response("POST", "/privacy")
    assert status == 405
    assert headers["allow"] == "GET"
    assert payload == {"error": "method_not_allowed"}


def test_remote_application_keeps_mcp_default_scope_without_metadata_scope():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteApplication(metadata)

    assert app.oauth.default_scope == "chatgpt-logs"
