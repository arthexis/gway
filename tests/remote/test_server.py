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

    assert source.operations == frozenset({"source", "search.source"})
    assert source.environment == frozenset()
    assert source.operations.isdisjoint(logs.operations)


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
            "products",
            "extensions",
            "service.list",
            "service.status",
            "sous.chef.list",
            "sous.chef.inspect",
        }
    )
    assert operator.environment == frozenset()
    assert logs.operations.isdisjoint(operator.operations)
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


def test_remote_runtime_converges_arthexis_scopes(tmp_path):
    from gway.gateway import Gateway
    from gway.security.scopes import ScopeRegistry

    runtime = Gateway()
    runtime.security_path = tmp_path / "security.sqlite"
    metadata = RemoteOAuthMetadata.from_origin("https://remote.example.test")

    RemoteApplication(metadata, runtime=runtime)

    registry = ScopeRegistry(runtime.security_path)
    read_scope = registry.require("arthexis-read")
    write_scope = registry.require("arthexis-write")

    assert read_scope.operations == frozenset(
        {
            "arthexis.fleet",
            "arthexis.ocpp_status",
            "arthexis.ocpp_matrix",
            "ocpp.charger",
            "ocpp.charger.enabled",
            "ocpp.charger.disabled",
            "ocpp.charger.connected",
            "ocpp.charger.disconnected",
            "ocpp.charger.charging",
            "ocpp.charger.idle",
            "ocpp.charger.unresolved",
            "ocpp.charger.historical",
            "ocpp.connector.all",
            "ocpp.connector.filter",
            "ocpp.chargerconnection.all",
            "ocpp.chargerconnection.filter",
            "ocpp.ocpptransaction.all",
            "ocpp.ocpptransaction.filter",
            "ocpp.metervalue.all",
            "ocpp.metervalue.filter",
            "ocpp.meterreadingbatch.all",
            "ocpp.meterreadingbatch.filter",
            "ocpp.protocoloperation.all",
            "ocpp.protocoloperation.filter",
            "ocpp.reservation.all",
            "ocpp.reservation.filter",
            "ocpp.chargervariable.all",
            "ocpp.chargervariable.filter",
            "ocpp.notificationrecord.all",
            "ocpp.notificationrecord.filter",
            "ocpp.monitoringrecord.all",
            "ocpp.monitoringrecord.filter",
            "ocpp.compatibilityevidence.all",
            "ocpp.compatibilityevidence.filter",
            "ocpp.chargingprofile.all",
            "ocpp.chargingprofile.filter",
            "ocpp.certificaterecord.all",
            "ocpp.certificaterecord.filter",
            "ocpp.inboundprotocolrequest.all",
            "ocpp.inboundprotocolrequest.filter",
            "ocpp.operationalstatusrecord.all",
            "ocpp.operationalstatusrecord.filter",
            "ocpp.chargertimelineprogress.all",
            "ocpp.chargertimelineprogress.filter",
            "energy.customeraccount.all",
            "energy.customeraccount.filter",
            "energy.energytariff.all",
            "energy.energytariff.filter",
            "energy.ledgerentry.all",
            "energy.ledgerentry.filter",
            "cards.cardcredential.all",
            "cards.cardcredential.filter",
            "cards.authorizationattempt.all",
            "cards.authorizationattempt.filter",
            "nodes.node.all",
            "nodes.node.filter",
            "nodes.nodelink.all",
            "nodes.nodelink.filter",
            "events.eventenvelope.all",
            "events.eventenvelope.filter",
        }
    )
    assert write_scope.operations == frozenset(
        {
            "ocpp.charger.reset",
            "ocpp.charger.start",
            "ocpp.charger.stop",
            "arthexis.event",
            "arthexis.ocpp_cutover",
            "arthexis.ocpp_policy",
            "arthexis.ocpp_recovery",
        }
    )
    assert read_scope.environment == frozenset()
    assert write_scope.environment == frozenset()
    assert read_scope.operations.isdisjoint(write_scope.operations)
