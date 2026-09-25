import pytest

from gway.appspec import AppSpec, RouteSpec, ViewSpec


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
