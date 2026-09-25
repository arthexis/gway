import pytest

from gway.sampler import load as load_sampler

web_app = load_sampler("web/app")
ApplicationHTTPAdapter = web_app.ApplicationHTTPAdapter
AppSpec = web_app.AppSpec
BindingSpec = web_app.BindingSpec
ViewSpec = web_app.ViewSpec


def test_view_declares_query_bindings_and_reuses_gway_coercion(gateway):
    def search(q, limit: int = 20):
        return {"q": q, "limit": limit}

    gateway.wrap("catalog.search", search)
    gateway("setup app --topic catalog")
    app = gateway("view search --route /search --query q,limit")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "GET",
        "/search?q=charger&limit=10",
    ) == (
        200,
        {},
        {"q": "charger", "limit": 10},
    )

    assert application.response(
        "GET",
        "/search?q=charger",
    ) == (
        200,
        {},
        {"q": "charger", "limit": 20},
    )


def test_path_bindings_match_named_route_segments(gateway):
    def user(user_id: int):
        return {"id": user_id}

    gateway.wrap("catalog.user", user)
    gateway("setup app --topic catalog")
    app = gateway(
        "view user --route /users/{user_id} --path-params user_id"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/users/42") == (
        200,
        {},
        {"id": 42},
    )


def test_literal_route_wins_over_path_template(gateway):
    gateway.wrap("catalog.named", lambda: {"kind": "literal"})
    gateway.wrap("catalog.user", lambda user_id: {"kind": "user", "id": user_id})
    gateway("setup app --topic catalog")
    gateway("view user --route /users/{user_id} --path-params user_id")
    app = gateway("view named --route /users/new")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response("GET", "/users/new") == (
        200,
        {},
        {"kind": "literal"},
    )


def test_equivalent_path_template_shapes_conflict():
    first = ViewSpec(
        "catalog.by_id",
        route="/users/{user_id}",
        bindings=(BindingSpec("user_id", "path"),),
    )
    second = ViewSpec(
        "catalog.by_name",
        route="/users/{name}",
        bindings=(BindingSpec("name", "path"),),
    )

    with pytest.raises(ValueError, match="Conflicting view"):
        AppSpec(views=(first, second))


def test_header_binding_uses_http_hyphen_spelling(gateway):
    gateway.wrap("catalog.mode", lambda x_mode: {"mode": x_mode})
    gateway("setup app --topic catalog")
    app = gateway("view mode --route /mode --header x_mode")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "GET",
        "/mode",
        headers={"X-Mode": "preview"},
    ) == (
        200,
        {},
        {"mode": "preview"},
    )


def test_single_body_binding_receives_decoded_json_payload(gateway):
    def create(payload):
        return {"name": payload["name"]}

    gateway.wrap("catalog.create", create)
    gateway("setup app --topic catalog")
    app = gateway(
        "view create --route /items --method POST --body payload"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "POST",
        "/items",
        headers={"content-type": "application/json"},
        body=b'{"name":"charger"}',
    ) == (
        200,
        {},
        {"name": "charger"},
    )


def test_multiple_body_bindings_extract_json_object_fields(gateway):
    def create(name, enabled: bool):
        return {"name": name, "enabled": enabled}

    gateway.wrap("catalog.create", create)
    gateway("setup app --topic catalog")
    app = gateway(
        "view create --route /items --method POST --body name,enabled"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "POST",
        "/items",
        headers={"content-type": "application/json"},
        body=b'{"name":"charger","enabled":true}',
    ) == (
        200,
        {},
        {"name": "charger", "enabled": True},
    )


def test_invalid_json_body_returns_400(gateway):
    gateway.wrap("catalog.create", lambda payload: payload)
    gateway("setup app --topic catalog")
    app = gateway(
        "view create --route /items --method POST --body payload"
    )
    application = ApplicationHTTPAdapter(gateway, app)

    status, _, payload = application.response(
        "POST",
        "/items",
        headers={"content-type": "application/json"},
        body=b"{broken",
    )

    assert status == 400
    assert payload["error"] == "invalid_request"


def test_missing_required_declared_input_returns_400(gateway):
    gateway.wrap("catalog.search", lambda q: q)
    gateway("setup app --topic catalog")
    app = gateway("view search --route /search --query q")
    application = ApplicationHTTPAdapter(gateway, app)

    status, _, payload = application.response("GET", "/search")

    assert status == 400
    assert payload["error"] == "invalid_request"
    assert "missing required argument" in payload["message"]


def test_undeclared_query_parameters_are_not_forwarded(gateway):
    def search(q):
        return q

    gateway.wrap("catalog.search", search)
    gateway("setup app --topic catalog")
    app = gateway("view search --route /search --query q")
    application = ApplicationHTTPAdapter(gateway, app)

    assert application.response(
        "GET",
        "/search?q=charger&admin=true",
    ) == (200, {}, "charger")
