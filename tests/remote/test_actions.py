import json

from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.actions import MAX_ACTION_COMMAND_BYTES, ActionsApplication
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def _remote(gateway, *, operations):
    scopes = ScopeRegistry(gateway.security_path)
    tokens = TokenRegistry(gateway.security_path)
    scopes.replace("actions-test", operations=set(operations))
    tokens.remove("actions-client")
    issued = tokens.create("actions-client", scopes={"actions-test"})
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    return ActionsApplication(metadata, runtime=gateway), issued.bearer


def _post(application, bearer, route, command):
    return application.response(
        "POST",
        route,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        body=json.dumps({"command": command}).encode("utf-8"),
    )


def test_actions_query_executes_with_read_only_ceiling(gateway):
    seen = []

    def observe(*, mutate=False):
        seen.append(mutate)
        return {"status": "ok"}

    gateway.observe = gateway.wrap("observe", observe)
    application, bearer = _remote(gateway, operations={"observe"})

    status, headers, payload = _post(
        application,
        bearer,
        "/actions/query",
        "observe",
    )

    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert payload == {"result": {"status": "ok"}}
    assert seen == [False]


def test_actions_query_blocks_mutation_before_invocation(gateway):
    called = []

    def restart():
        called.append(True)
        return "restarted"

    gateway.restart = gateway.wrap("restart", restart)
    application, bearer = _remote(gateway, operations={"restart"})

    status, _, payload = _post(
        application,
        bearer,
        "/actions/query",
        "restart",
    )

    assert status == 409
    assert payload["error"] == "mutation_not_allowed"
    assert called == []


def test_actions_execute_uses_normal_external_mutation_policy(gateway):
    called = []

    def restart():
        called.append(True)
        return "restarted"

    gateway.restart = gateway.wrap("restart", restart)
    application, bearer = _remote(gateway, operations={"restart"})

    status, _, payload = _post(
        application,
        bearer,
        "/actions/execute",
        "restart",
    )

    assert status == 200
    assert payload == {"result": "restarted"}
    assert called == [True]


def test_actions_execute_still_requires_named_scope_authorization(gateway):
    def restart():
        return "restarted"

    gateway.restart = gateway.wrap("restart", restart)
    application, bearer = _remote(gateway, operations=set())

    status, _, payload = _post(
        application,
        bearer,
        "/actions/execute",
        "restart",
    )

    assert status == 403
    assert payload["error"] == "not_authorized"


def test_actions_require_bearer(gateway):
    application, _ = _remote(gateway, operations=set())

    status, headers, payload = application.response(
        "POST",
        "/actions/query",
        headers={"Content-Type": "application/json"},
        body=b'{"command":"help log read"}',
    )

    assert status == 401
    assert headers["www-authenticate"] == "Bearer"
    assert payload == {"error": "invalid_bearer"}


def test_actions_validate_json_request_shape(gateway):
    application, bearer = _remote(gateway, operations=set())
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }

    status, _, payload = application.response(
        "POST",
        "/actions/query",
        headers=headers,
        body=b"not-json",
    )
    assert status == 400
    assert payload["error"] == "invalid_request"

    status, _, payload = application.response(
        "POST",
        "/actions/query",
        headers=headers,
        body=b"[]",
    )
    assert status == 400
    assert payload["error"] == "invalid_request"

    status, _, payload = application.response(
        "POST",
        "/actions/query",
        headers=headers,
        body=b"{}",
    )
    assert status == 400
    assert payload["error"] == "invalid_request"


def test_actions_reject_oversized_commands(gateway):
    application, bearer = _remote(gateway, operations=set())
    oversized = "x" * (MAX_ACTION_COMMAND_BYTES + 1)

    status, _, payload = _post(
        application,
        bearer,
        "/actions/query",
        oversized,
    )

    assert status == 400
    assert payload["error"] == "query_too_large"


def test_actions_allow_only_post(gateway):
    application, bearer = _remote(gateway, operations=set())
    headers = {"Authorization": f"Bearer {bearer}"}

    for route in ("/actions/query", "/actions/execute"):
        status, response_headers, payload = application.response(
            "GET",
            route,
            headers=headers,
        )
        assert status == 405
        assert response_headers["allow"] == "POST"
        assert payload["error"] == "method_not_allowed"


def test_actions_reject_invalid_utf8_json(gateway):
    application, bearer = _remote(gateway, operations=set())

    status, _, payload = application.response(
        "POST",
        "/actions/query",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        body=b"\xff",
    )

    assert status == 400
    assert payload["error"] == "invalid_request"


def test_actions_results_are_json_safe(gateway):
    def values():
        return {"items": {"one", "two"}}

    gateway.values = gateway.wrap("values", values)
    application, bearer = _remote(gateway, operations={"values"})

    status, _, payload = _post(
        application,
        bearer,
        "/actions/execute",
        "values",
    )

    assert status == 200
    assert sorted(payload["result"]["items"]) == ["one", "two"]
    json.dumps(payload)


def test_remote_server_delegates_actions_namespace(gateway):
    from gway.remote.server import RemoteApplication

    scopes = ScopeRegistry(gateway.security_path)
    tokens = TokenRegistry(gateway.security_path)
    scopes.replace("actions-delegation", operations={"help"})
    tokens.remove("actions-delegation-client")
    issued = tokens.create(
        "actions-delegation-client",
        scopes={"actions-delegation"},
    )
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    application = RemoteApplication(metadata, runtime=gateway)

    status, _, payload = _post(
        application,
        issued.bearer,
        "/actions/query",
        "help help",
    )

    assert status == 200
    assert "result" in payload
