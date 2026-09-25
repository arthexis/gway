import pytest

from gway.appadapter import (
    HandlerNotFound,
    InMemoryAdapter,
    MethodNotAllowed,
    RouteNotFound,
)
from gway.appspec import AppSpec, ViewSpec
from gway.ingestion.base import remember_object
from gway.ingestion.python import ingest_python
def _register_handler(gateway, name):
    def handler():
        return name

    return gateway.wrap(name, handler)


def test_setup_app_publishes_framework_neutral_app(gateway):
    app = gateway("setup app remote")

    assert app == AppSpec(name="remote")
    assert gateway.results["app"] is app


def test_view_app_reuses_semantic_app_and_stores_canonical_handler(gateway):
    _register_handler(gateway, "remote.health")
    original = gateway("setup app remote")

    updated = gateway("view app remote.health --route /health")

    assert original.views == ()
    assert updated is gateway.results["app"]
    assert updated.views[0].callable_name == "remote.health"
    assert updated.views[0].resolved_route == "/health"


def test_view_shorthand_resolves_unique_handler_leaf(gateway):
    _register_handler(gateway, "remote.health_status")
    gateway("setup app remote")

    updated = gateway("view health_status")

    assert updated.views[0].callable_name == "remote.health_status"
    assert updated.views[0].resolved_route == "/health-status"


def test_view_methods_use_existing_sequence_argument_semantics(gateway):
    _register_handler(gateway, "remote.consent")
    gateway("setup app remote")

    updated = gateway(
        "view consent --route /consent --methods GET,POST",
    )

    assert updated.views[0].methods == ("GET", "POST")


def test_view_accepts_singular_method_alias(gateway):
    _register_handler(gateway, "remote.create_user")
    gateway("setup app remote")

    updated = gateway("view create_user --method POST")

    assert updated.views[0].methods == ("POST",)


def test_view_rejects_ambiguous_short_handler_identity(gateway):
    _register_handler(gateway, "remote.health")
    _register_handler(gateway, "admin.health")
    gateway("setup app remote")

    with pytest.raises(LookupError, match="Ambiguous view handler"):
        gateway("view health")


def test_view_rejects_unknown_handler_identity(gateway):
    gateway("setup app remote")

    with pytest.raises(LookupError, match="Unknown view handler operation"):
        gateway("view missing_handler")


def test_view_replace_only_replaces_claimed_route_methods(gateway):
    _register_handler(gateway, "remote.resource")
    _register_handler(gateway, "remote.override")
    gateway("setup app remote")
    gateway("view resource --route /resource --methods GET,POST")

    updated = gateway(
        "view override --route /resource --method GET --replace",
    )

    assert [(route.method, route.handler) for route in updated.routes] == [
        ("POST", "remote.resource"),
        ("GET", "remote.override"),
    ]


def test_app_composition_operations_are_declared_non_mutating(gateway):
    assert gateway.setup_app.mutates is False
    assert gateway.view_app.mutates is False

    app = gateway.execute("setup app remote", mutate=False)

    assert app == AppSpec(name="remote")


def test_recipe_companion_handler_composes_by_short_identity(gateway, tmp_path):
    recipe = tmp_path / "remote.rx"
    recipe.write_text(
        "setup app remote\n"
        "view health_status --route /health\n",
        encoding="utf-8",
    )
    recipe.with_suffix(".py").write_text(
        "def health_status():\n"
        "    return {'status': 'ok'}\n",
        encoding="utf-8",
    )

    app = gateway(recipe)

    assert app.name == "remote"
    assert app.views[0].callable_name == "remote.health_status"
    assert app.views[0].resolved_route == "/health"



def test_in_memory_adapter_dispatches_get_and_preserves_return_value(gateway):
    def health(name="world"):
        return {"hello": name}

    gateway.wrap("remote.health", health)
    app = gateway("setup app remote")
    app = gateway("view health --route /health")

    adapter = InMemoryAdapter(gateway, app)

    assert adapter.request("/health", arguments={"name": "Ada"}) == {"hello": "Ada"}


def test_in_memory_adapter_dispatches_method_specific_handlers(gateway):
    gateway.wrap("remote.read_resource", lambda resource_id: f"read:{resource_id}")
    gateway.wrap("remote.write_resource", lambda resource_id: f"write:{resource_id}")
    gateway("setup app remote")
    gateway("view read_resource --route /resource --method GET")
    app = gateway("view write_resource --route /resource --method POST")

    adapter = InMemoryAdapter(gateway, app)

    assert adapter.request("/resource", "GET", arguments={"resource_id": "42"}) == "read:42"
    assert adapter.request("/resource", "post", arguments={"resource_id": "42"}) == "write:42"


def test_in_memory_adapter_reports_missing_route(gateway):
    adapter = InMemoryAdapter(gateway, AppSpec())

    with pytest.raises(RouteNotFound, match=r"No route registered for /missing"):
        adapter.request("/missing")


def test_in_memory_adapter_reports_disallowed_method(gateway):
    gateway.wrap("remote.health", lambda: "ok")
    gateway("setup app remote")
    app = gateway("view health --route /health --method GET")

    adapter = InMemoryAdapter(gateway, app)

    with pytest.raises(
        MethodNotAllowed,
        match=r"POST is not allowed for /health; allowed methods: GET",
    ):
        adapter.request("/health", "POST")


def test_in_memory_adapter_reports_unavailable_handler(gateway):
    app = AppSpec().add(
        ViewSpec(
            "remote.missing",
            route="/missing-handler",
        )
    )
    adapter = InMemoryAdapter(gateway, app)

    with pytest.raises(HandlerNotFound, match="remote.missing"):
        adapter.request("/missing-handler")


def test_in_memory_adapter_uses_gateway_signature_binding_errors(gateway):
    def create_user(name, age: int):
        return {"name": name, "age": age}

    gateway.wrap("remote.create_user", create_user)
    gateway("setup app remote")
    app = gateway("view create_user --route /users --method POST")
    adapter = InMemoryAdapter(gateway, app)

    with pytest.raises(TypeError, match="missing required argument: age"):
        adapter.request("/users", "POST", arguments={"name": "Ada"})



def test_view_resolves_lazy_handler_through_normal_jit_ingestion(gateway):
    class LazyHandlers:
        def health(self):
            return "ok"

    source = LazyHandlers()
    remember_object(
        gateway,
        source,
        ("lazy",),
        expander=ingest_python,
    )
    gateway("setup app remote")

    app = gateway("view lazy.health --route /health")

    assert app.views[0].callable_name == "lazy.health"


def test_in_memory_adapter_resolves_lazy_handler_before_invocation(gateway):
    class LazyHandlers:
        def health(self, name):
            return f"hello:{name}"

    source = LazyHandlers()
    remember_object(
        gateway,
        source,
        ("lazy",),
        expander=ingest_python,
    )
    app = AppSpec().add(ViewSpec("lazy.health", route="/health"))
    adapter = InMemoryAdapter(gateway, app)

    assert adapter.request("/health", arguments={"name": "Ada"}) == "hello:Ada"


def test_in_memory_adapter_forwards_handler_arguments_named_route_and_method(gateway):
    def echo(route, method):
        return route, method

    gateway.wrap("remote.echo", echo)
    gateway("setup app remote")
    app = gateway("view echo --route /echo")
    adapter = InMemoryAdapter(gateway, app)

    assert adapter.request(
        "/echo",
        arguments={"route": "handler-route", "method": "handler-method"},
    ) == ("handler-route", "handler-method")


def test_setup_app_infers_name_from_topic_and_composes_base_route(gateway):
    gateway.wrap("remote.settings.profile", lambda: "profile")

    app = gateway("setup app --topic remote.settings --route /settings")
    app = gateway("view profile")

    assert app.name == "settings"
    assert app.topic == "remote.settings"
    assert app.route == "/settings"
    assert [(route.route, route.handler) for route in app.routes] == [
        ("/settings/profile", "remote.settings.profile")
    ]


def test_app_topic_preferred_over_ambiguous_global_leaf(gateway):
    gateway.wrap("remote.browser.connect", lambda: "browser")
    gateway.wrap("admin.connect", lambda: "admin")

    gateway("setup app --topic remote.browser")
    app = gateway("view connect")

    assert app.views[0].callable_name == "remote.browser.connect"


def test_explicit_app_name_overrides_topic_inference(gateway):
    app = gateway("setup app portal --topic remote.browser")

    assert app.name == "portal"
    assert app.topic == "remote.browser"


def test_start_app_consumes_semantic_app_context(gateway, monkeypatch):
    calls = {}

    def fake_serve(runtime, app, host="127.0.0.1", port=8000, *, context=None):
        calls.update(
            runtime=runtime,
            app=app,
            host=host,
            port=port,
            context=context,
        )
        return "served"

    monkeypatch.setattr("gway.appserver.serve_app", fake_serve)
    app = gateway("setup app --topic demo")

    result = gateway("start app --host 127.0.0.2 --port 8123")

    assert result == "served"
    assert calls == {
        "runtime": gateway,
        "app": app,
        "host": "127.0.0.2",
        "port": 8123,
        "context": None,
    }


def test_start_app_is_mutating_lifecycle_operation(gateway):
    assert gateway.start_app.mutates is True
