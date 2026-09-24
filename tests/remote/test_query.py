from urllib.parse import urlencode

from gway.remote.metadata import RemoteOAuthMetadata
from gway.remote.server import MAX_QUERY_COMMAND_BYTES, RemoteApplication
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


RESOURCE = "https://remote.example.test/mcp"


def _remote(gateway, *, operations):
    scopes = ScopeRegistry(gateway.security_path)
    tokens = TokenRegistry(gateway.security_path)
    scopes.replace("query-test", operations=set(operations))
    tokens.remove("query-client")
    issued = tokens.create("query-client", scopes={"query-test"})
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    return RemoteApplication(metadata, runtime=gateway), issued.bearer


def _get(application, bearer, command):
    path = "/query?" + urlencode({"c": command})
    return application.response(
        "GET",
        path,
        headers={"Authorization": f"Bearer {bearer}"},
    )


def test_query_executes_authorized_non_mutating_operation(gateway):
    seen = []

    def observe(*, mutate=False):
        seen.append(mutate)
        return {"status": "ok"}

    gateway.observe = gateway.wrap("observe", observe)
    application, bearer = _remote(gateway, operations={"observe"})

    status, headers, payload = _get(application, bearer, "observe")

    assert status == 200
    assert headers["cache-control"] == "no-store"
    assert payload == {"result": {"status": "ok"}}
    assert seen == [False]


def test_query_rejects_mutating_operation_before_invocation(gateway):
    called = []

    def restart():
        called.append(True)
        return "restarted"

    gateway.restart = gateway.wrap("restart", restart)
    application, bearer = _remote(gateway, operations={"restart"})

    status, _, payload = _get(application, bearer, "restart")

    assert status == 409
    assert payload["error"] == "mutation_not_allowed"
    assert called == []


def test_query_distinguishes_authorization_from_mutation(gateway):
    def observe(*, mutate=False):
        return "ok"

    gateway.observe = gateway.wrap("observe", observe)
    application, bearer = _remote(gateway, operations=set())

    status, _, payload = _get(application, bearer, "observe")

    assert status == 403
    assert payload["error"] == "not_authorized"


def test_query_requires_authorization_header(gateway):
    application, _ = _remote(gateway, operations=set())

    status, headers, payload = application.response("GET", "/query?c=observe")

    assert status == 401
    assert headers["www-authenticate"] == "Bearer"
    assert payload == {"error": "invalid_bearer"}


def test_query_preserves_url_encoded_command_text(gateway):
    def echo(value, *, mutate=False):
        return value

    gateway.echo = gateway.wrap("echo", echo)
    application, bearer = _remote(gateway, operations={"echo"})
    expected = "a&b ? c/#"

    status, _, payload = _get(
        application,
        bearer,
        f'echo "{expected}"',
    )

    assert status == 200
    assert payload == {"result": expected}


def test_query_rejects_missing_empty_or_oversized_command(gateway):
    application, bearer = _remote(gateway, operations=set())
    headers = {"Authorization": f"Bearer {bearer}"}

    status, _, payload = application.response("GET", "/query", headers=headers)
    assert status == 400
    assert payload["error"] == "invalid_query"

    status, _, payload = application.response("GET", "/query?c=", headers=headers)
    assert status == 400
    assert payload["error"] == "invalid_query"

    oversized = "x" * (MAX_QUERY_COMMAND_BYTES + 1)
    status, _, payload = application.response(
        "GET",
        "/query?" + urlencode({"c": oversized}),
        headers=headers,
    )
    assert status == 400
    assert payload["error"] == "query_too_large"


def test_query_allows_only_get(gateway):
    application, bearer = _remote(gateway, operations=set())

    status, headers, payload = application.response(
        "POST",
        "/query?c=observe",
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert status == 405
    assert headers["allow"] == "GET"
    assert payload["error"] == "method_not_allowed"


def test_repeated_query_does_not_accumulate_gateway_bookkeeping(gateway):
    def observe(*, mutate=False):
        return "ok"

    gateway.observe = gateway.wrap("observe", observe)
    application, bearer = _remote(gateway, operations={"observe"})
    initial_context = dict(gateway.context)
    initial_results = dict(gateway.results.get_results())
    initial_history = list(gateway.results.history)

    for _ in range(10):
        status, _, payload = _get(application, bearer, "observe")
        assert status == 200
        assert payload == {"result": "ok"}

    assert gateway.context == initial_context
    assert gateway.results.get_results() == initial_results
    assert gateway.results.history == initial_history
