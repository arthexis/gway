from urllib.parse import urlencode


from gway.config import bootstrap
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


def test_full_access_scope_authorizes_operation_added_after_token_creation(gateway):
    scopes = ScopeRegistry(gateway.security_path)
    tokens = TokenRegistry(gateway.security_path)
    scopes.replace(
        "full-access",
        operations={"__all__"},
        environment={"__all__"},
    )
    issued = tokens.create("full-client", scopes={"full-access"})

    def future(*, mutate=False):
        return "future-ok"

    gateway.future = gateway.wrap("future.operation", future)
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    application = RemoteApplication(metadata, runtime=gateway)

    status, _, payload = _get(application, issued.bearer, "future")

    assert status == 200
    assert payload == {"result": "future-ok"}


def test_read_scopes_include_watch(gateway):
    metadata = RemoteOAuthMetadata.from_origin(
        "https://remote.example.test",
        resource_path="/mcp",
    )
    RemoteApplication(metadata, runtime=gateway)
    scopes = ScopeRegistry(gateway.security_path)

    for name in ("logs-read", "source-read", "operator-read"):
        assert "watch" in scopes.require(name).operations


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


def _watch_gateway(gateway, tmp_path, monkeypatch, *, role="control"):
    (tmp_path / "pyproject.toml").write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
role = "{role}"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    bootstrap(gateway, start=tmp_path)
    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: {"ready": True},
        op="check",
        sub="wire",
    )
    gateway.wrap(
        "log.search",
        lambda pattern, *source, since=None, until=None, limit=100, all=False, mutate=False: [],
        op="search",
        sub="log",
    )
    return gateway


def test_remote_query_executes_first_class_watch_under_no_mutate(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)
    application, bearer = _remote(
        gateway,
        operations={
            "watch",
            "node",
            "service.statuses",
            "wire.check",
            "log.search",
        },
    )

    status, headers, payload = _get(application, bearer, "watch --only node,wire")

    assert status == 200
    assert headers["cache-control"] == "no-store"
    result = payload["result"]
    assert set(result) == {"node", "wire", "health", "changed_at", "cursor"}
    assert result["node"]["status"] == "ok"
    assert result["wire"]["status"] == "ok"
    assert result["health"]["status"] == "ok"
    assert isinstance(result["cursor"], str)
    assert result["cursor"]


def test_remote_watch_reduces_output_to_component_scope(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)
    application, bearer = _remote(
        gateway,
        operations={"watch", "node"},
    )

    status, _, payload = _get(application, bearer, "watch")

    assert status == 200
    result = payload["result"]
    assert set(result) == {"node", "health", "changed_at", "cursor"}
    assert result["node"]["status"] == "ok"
    assert result["health"]["sections"] == {"node": "ok"}


def test_remote_watch_blocks_mutating_component_without_side_effect(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)
    calls = []

    def mutate_wire():
        calls.append("mutated")
        return {"ready": True}

    gateway.wrap("wire.check", mutate_wire, op="check", sub="wire")
    application, bearer = _remote(
        gateway,
        operations={"watch", "wire.check"},
    )

    status, _, payload = _get(application, bearer, "watch --only wire")

    assert status == 200
    result = payload["result"]
    assert result["wire"]["status"] == "blocked"
    assert result["health"]["status"] == "degraded"
    assert result["health"]["degraded"] == ["wire"]
    assert calls == []


def test_remote_watch_aggregates_authorized_published_contributor(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)

    def product_status(*, mutate=False):
        return {"ready": True}

    gateway.wrap("demo.status", product_status, op="status", sub="demo")
    gateway._watch_contributors = (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )
    application, bearer = _remote(
        gateway,
        operations={"watch", "demo.status"},
    )

    status, _, payload = _get(application, bearer, "watch --only demo")

    assert status == 200, payload
    result = payload["result"]
    assert result["demo"]["status"] == "ok"
    assert result["demo"]["result"] == {"ready": True}
    assert result["health"]["sections"] == {"demo": "ok"}


def test_remote_watch_omits_unauthorized_published_contributor(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)
    gateway.wrap(
        "demo.status",
        lambda *, mutate=False: {"ready": True},
        op="status",
        sub="demo",
    )
    gateway._watch_contributors = (
        {
            "section": "demo",
            "command": ("demo", "status"),
            "source": "demo",
        },
    )
    application, bearer = _remote(gateway, operations={"watch"})

    status, _, payload = _get(application, bearer, "watch")

    assert status == 200
    assert "demo" not in payload["result"]


def test_remote_watch_missing_component_scope_is_not_transport_error(
    gateway,
    tmp_path,
    monkeypatch,
):
    _watch_gateway(gateway, tmp_path, monkeypatch)
    application, bearer = _remote(
        gateway,
        operations={"watch"},
    )

    status, _, payload = _get(application, bearer, "watch")

    assert status == 200
    result = payload["result"]
    assert set(result) == {"health", "changed_at", "cursor"}
    assert result["health"] == {
        "status": "ok",
        "sections": {},
        "counts": {},
        "degraded": [],
    }
