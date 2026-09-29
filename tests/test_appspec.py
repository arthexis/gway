import pytest

from gway.sampler import load as load_sampler

web_app = load_sampler("web/app")
AppSpec = web_app.AppSpec
HeaderSpec = web_app.HeaderSpec
RouteSpec = web_app.RouteSpec
ViewSpec = web_app.ViewSpec


def test_app_spec_composes_views_without_mutating_original():
    app = AppSpec(name="remote")
    view = ViewSpec("remote.health", route="/health")

    updated = app.add(view)

    assert app.views == ()
    assert updated.views == (view,)


def test_app_spec_add_is_idempotent_for_same_view():
    view = ViewSpec("remote.health", route="/health")
    app = AppSpec(name="remote").add(view)

    assert app.add(view) is app


def test_app_spec_constructor_deduplicates_same_view():
    view = ViewSpec("remote.health", route="/health")

    app = AppSpec(views=(view, view))

    assert app.views == (view,)


def test_view_defaults_to_get():
    assert ViewSpec("remote.health").methods == ("GET",)


def test_view_infers_route_from_callable_name():
    assert ViewSpec("remote.health_status").resolved_route == "/health-status"


def test_view_compiles_deterministic_route_specs():
    view = ViewSpec("remote.consent", route="/consent", methods=("get", "POST", "GET"))

    assert view.methods == ("GET", "POST")
    assert view.routes == (
        RouteSpec("/consent", "GET", "remote.consent"),
        RouteSpec("/consent", "POST", "remote.consent"),
    )


def test_app_spec_rejects_conflicting_route_method():
    app = AppSpec().add(ViewSpec("remote.first", route="/health"))

    with pytest.raises(ValueError, match=r"Conflicting view for GET /health"):
        app.add(ViewSpec("remote.second", route="/health"))


def test_app_spec_constructor_rejects_conflicting_route_method():
    with pytest.raises(ValueError, match=r"Conflicting view for GET /health"):
        AppSpec(
            views=(
                ViewSpec("remote.first", route="/health"),
                ViewSpec("remote.second", route="/health"),
            )
        )


def test_app_spec_allows_same_route_with_distinct_methods():
    app = AppSpec().add(ViewSpec("remote.read", route="/resource", methods=("GET",)))

    updated = app.add(ViewSpec("remote.write", route="/resource", methods=("POST",)))

    assert [route.method for route in updated.routes] == ["GET", "POST"]



def test_app_spec_headers_are_copy_on_write():
    app = AppSpec(name="remote")

    updated = app.with_header("Cache-Control", "no-store")

    assert app.headers == ()
    assert updated.headers == (HeaderSpec("cache-control", "no-store"),)


def test_app_spec_header_names_are_semantic_and_case_insensitive():
    app = AppSpec().with_header("Cache-Control", "public")

    updated = app.with_header("cache-control", "no-store")

    assert updated.headers == (HeaderSpec("cache-control", "no-store"),)


def test_app_spec_preserves_headers_when_adding_view():
    app = AppSpec().with_header("X-Test", "one")

    updated = app.add(ViewSpec("remote.health", route="/health"))

    assert app.views == ()
    assert updated.headers == app.headers
    assert updated.views[0].callable_name == "remote.health"


def test_app_spec_constructor_keeps_last_value_for_duplicate_header():
    app = AppSpec(
        headers=(
            HeaderSpec("X-Test", "one"),
            HeaderSpec("x-test", "two"),
        )
    )

    assert app.headers == (HeaderSpec("x-test", "two"),)



def test_header_spec_rejects_response_splitting():
    with pytest.raises(ValueError, match="line breaks"):
        HeaderSpec("X-Test", "safe\r\nX-Evil: yes")


def test_header_spec_rejects_invalid_name_token():
    with pytest.raises(ValueError, match="HTTP token"):
        HeaderSpec("Bad Header", "value")
