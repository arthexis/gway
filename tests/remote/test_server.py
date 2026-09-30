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


def test_remote_application_uses_full_access_default_scope():
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteApplication(metadata)

    assert app.oauth.default_scope == "full-access"


def test_remote_custom_account_converges_full_access_in_account_registry(tmp_path):
    from gway.remote.account import RemoteAccountApplication
    from gway.remote.session import RemoteSessionStore
    from gway.security.oauth import OAuthRegistry
    from gway.security.tokens import TokenRegistry

    path = tmp_path / "custom-security.sqlite"
    account = RemoteAccountApplication(
        oauth=OAuthRegistry(path),
        tokens=TokenRegistry(path),
        sessions=RemoteSessionStore(),
    )
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, account=account)

    scope = account.oauth.scopes.require("full-access")
    assert scope.operations == frozenset({"__all__"})
    assert scope.environment == frozenset({"__all__"})


def test_remote_runtime_converges_full_access_scope(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    scope = ScopeRegistry(runtime.security_path).require("full-access")
    assert scope.operations == frozenset({"__all__"})
    assert scope.environment == frozenset({"__all__"})


def test_remote_runtime_converges_logs_read_scope(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    scope = ScopeRegistry(runtime.security_path).require("logs-read")
    assert scope.operations == frozenset(
        {
            "survey",
            "help",
            "guide",
            "version",
            "log.sources",
            "log.read",
            "log.tail",
            "log.search",
            "security.whoami",
            "security.scope.current",
        }
    )
    assert scope.environment == frozenset()



def test_remote_runtime_converges_source_read_scope(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    registry = ScopeRegistry(runtime.security_path)
    source = registry.require("source-read")
    logs = registry.require("logs-read")

    assert source.operations == frozenset(
        {
            "survey",
            "source",
            "search.source",
            "node.deploy.status",
            "node.release.status",
            "node.queue.status",
        }
    )
    assert source.environment == frozenset()
    assert source.operations & logs.operations == frozenset({"survey"})


def test_remote_runtime_converges_source_admin_scope(tmp_path):
    from gway.gateway import Gateway
    from gway.githubops import ADMIN_OPERATIONS
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    registry = ScopeRegistry(runtime.security_path)
    admin = registry.require("source-admin")
    read = registry.require("source-read")

    assert admin.operations == frozenset(
        f"github.{name}" for name in ADMIN_OPERATIONS
    )
    assert admin.environment == frozenset()
    assert admin.operations.isdisjoint(read.operations)
    assert registry.resolve({"source-read", "source-admin"}).operations == (
        read.operations | admin.operations
    )


def test_remote_runtime_converges_operator_read_scope(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    registry = ScopeRegistry(runtime.security_path)
    logs = registry.require("logs-read")
    operator = registry.require("operator-read")

    assert operator.operations == frozenset(
        {
            "survey",
            "node",
            "products",
            "extensions",
            "builtins",
            "filter",
            "service.list",
            "service.status",
            "service.statuses",
            "wire.check",
            "sous.chef.list",
            "sous.chef.inspect",
        }
    )
    assert operator.environment == frozenset()
    assert logs.operations & operator.operations == frozenset({"survey"})
    assert registry.resolve({"logs-read", "operator-read"}).operations == (
        logs.operations | operator.operations
    )


def test_remote_runtime_permission_summary_expands_lazy_read_only_operation(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    ScopeRegistry(runtime.security_path).replace(
        "logs",
        operations={"log.read"},
        environment=(),
    )
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    app = RemoteApplication(metadata, runtime=runtime)

    assert runtime.ops.resolve("log.read") is None

    summary = app.account.permission_summary({"logs"})

    assert summary["effective"]["mutation_capable"] is False
    assert callable(runtime.ops.resolve("log.read"))


def test_remote_runtime_registers_product_published_scopes(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    runtime._published_scopes = {
        "demo-read": {
            "operations": frozenset({"demo.status"}),
            "environment": frozenset(),
            "source": "demo",
        }
    }
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    scope = ScopeRegistry(runtime.security_path).require("demo-read")
    assert scope.operations == frozenset({"demo.status"})
    assert scope.environment == frozenset()


def test_builtin_read_scope_union_covers_complete_builtin_survey(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")
    RemoteApplication(metadata, runtime=runtime)

    operations = ScopeRegistry(runtime.security_path).resolve(
        {"logs-read", "source-read", "operator-read"}
    ).operations
    assert {
        "survey",
        "node",
        "service.statuses",
        "node.deploy.status",
        "node.release.status",
        "node.queue.status",
        "wire.check",
        "log.search",
    } <= operations
