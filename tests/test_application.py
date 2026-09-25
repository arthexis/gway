import pytest

from gway.appspec import AppSpec
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
