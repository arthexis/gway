from types import SimpleNamespace

from gway.ingestion.base import IngestedObject
from gway.ingestion.django import DjangoProject
from gway.security.django_publication import (
    collect_django_publications,
    derive_django_publications,
)


def _gateway(product="demo", app_label="widgets"):
    app = SimpleNamespace(label=app_label)
    mount = DjangoProject(
        root=SimpleNamespace(),
        settings=None,
        name=product,
        registry=SimpleNamespace(),
        apps=(app,),
    )
    ingested = {1: IngestedObject(value=mount)}
    return SimpleNamespace(_ingested=ingested, _published_scopes={}, ops=None), app


def _operation(app, name, *, mutates):
    meta = SimpleNamespace(app_config=app)
    model = type("Model", (), {"_meta": meta})

    def invoke():
        return None

    invoke.__gway_source__ = model
    invoke.__gway_source_kind__ = "django-model"
    invoke.mutates = mutates
    return SimpleNamespace(name=name, callable=invoke)


def test_django_scopes_are_derived_from_product_app_and_mutation_contract():
    gateway, app = _gateway()
    gateway.ops = SimpleNamespace(
        records=lambda: (
            _operation(app, "widgets.list", mutates=False),
            _operation(app, "widgets.create", mutates=True),
        )
    )

    scopes = {scope.name: scope for scope in derive_django_publications(gateway)}

    assert set(scopes) == {"demo-widgets-read", "demo-widgets-write"}
    assert scopes["demo-widgets-read"].semantic_terms == frozenset(
        {"demo", "widgets", "read"}
    )
    assert scopes["demo-widgets-read"].operations == frozenset({"widgets.list"})
    assert scopes["demo-widgets-write"].operations == frozenset({"widgets.create"})
    assert scopes["demo-widgets-read"].source == "django:demo:widgets"


def test_new_app_name_changes_scope_without_gway_configuration():
    gateway, app = _gateway(app_label="gadgets")
    gateway.ops = SimpleNamespace(
        records=lambda: (_operation(app, "gadgets.list", mutates=False),)
    )

    scopes = derive_django_publications(gateway)

    assert [scope.name for scope in scopes] == ["demo-gadgets-read"]
    assert scopes[0].semantic_terms == frozenset({"demo", "gadgets", "read"})


def test_unowned_django_app_does_not_publish_authority():
    gateway, _ = _gateway()
    framework_app = SimpleNamespace(label="auth")
    gateway.ops = SimpleNamespace(
        records=lambda: (_operation(framework_app, "auth.list", mutates=False),)
    )

    assert derive_django_publications(gateway) == ()


def test_collect_replaces_old_derived_scopes_but_preserves_manual_publications():
    gateway, app = _gateway()
    gateway._published_scopes = {
        "manual-read": {
            "source": "demo",
            "operations": frozenset({"manual.list"}),
            "semantic_terms": frozenset({"manual", "read"}),
        },
        "demo-old-read": {
            "source": "django:demo:old",
            "operations": frozenset({"old.list"}),
            "semantic_terms": frozenset({"demo", "old", "read"}),
        },
    }
    gateway.ops = SimpleNamespace(
        records=lambda: (_operation(app, "widgets.list", mutates=False),)
    )

    published = collect_django_publications(gateway)

    assert set(published) == {"manual-read", "demo-widgets-read"}
    assert published["demo-widgets-read"]["semantic_terms"] == frozenset(
        {"demo", "widgets", "read"}
    )


def test_installed_app_without_operations_creates_no_scope():
    gateway, _ = _gateway()
    gateway.ops = SimpleNamespace(records=lambda: ())

    assert derive_django_publications(gateway) == ()
