from gway.appspec import AppSpec, ViewSpec


def test_app_spec_composes_views_without_mutating_original():
    app = AppSpec(name="remote")
    view = ViewSpec("remote.health", endpoint="/health")

    updated = app.add(view)

    assert app.views == ()
    assert updated.views == (view,)


def test_app_spec_add_is_idempotent_for_same_view():
    view = ViewSpec("remote.health", endpoint="/health")
    app = AppSpec(name="remote").add(view)

    assert app.add(view) is app


def test_view_defaults_to_get():
    assert ViewSpec("remote.health").methods == ("GET",)
