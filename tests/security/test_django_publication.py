from types import SimpleNamespace

import gway.security.django_publication as publication
from gway.ingestion.base import IngestedObject
from gway.ingestion.django import DjangoProject
from gway.security.django_publication import (
    collect_django_publications,
    derive_django_publications,
)


def _gateway(tmp_path, product="demo", app_label="widgets", app_name=None):
    root = tmp_path / product
    root.mkdir()
    app_root = root / app_label
    app_root.mkdir()
    app = SimpleNamespace(
        label=app_label,
        name=app_name or f"{product}.{app_label}",
        path=app_root,
    )
    mount = DjangoProject(
        root=root,
        settings=None,
        name=product,
        registry=SimpleNamespace(),
        apps=(app,),
    )
    ingested = {1: IngestedObject(value=mount)}
    return SimpleNamespace(_ingested=ingested, _published_scopes={}, ops=None), mount, app


def _operation(app, name, *, mutates):
    meta = SimpleNamespace(app_config=app)
    model = type("Model", (), {"_meta": meta})

    def invoke():
        return None

    invoke.__gway_source__ = model
    invoke.__gway_source_kind__ = "django-model"
    invoke.mutates = mutates
    return SimpleNamespace(name=name, callable=invoke)


def _command(mount, name, *, mutates):
    def invoke():
        return None

    invoke.__gway_source__ = mount
    invoke.__gway_source_kind__ = "django-command"
    invoke.__gway_metadata__ = {
        "project": mount.name,
        "command": name,
        "settings": mount.settings,
    }
    invoke.mutates = mutates
    return SimpleNamespace(name=f"{mount.name}.{name}", callable=invoke)


def test_django_scopes_are_derived_from_product_app_and_mutation_contract(tmp_path):
    gateway, _, app = _gateway(tmp_path)
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


def test_new_app_name_changes_scope_without_gway_configuration(tmp_path):
    gateway, _, app = _gateway(tmp_path, app_label="gadgets")
    gateway.ops = SimpleNamespace(
        records=lambda: (_operation(app, "gadgets.list", mutates=False),)
    )

    scopes = derive_django_publications(gateway)

    assert [scope.name for scope in scopes] == ["demo-gadgets-read"]
    assert scopes[0].semantic_terms == frozenset({"demo", "gadgets", "read"})


def test_app_outside_project_root_does_not_publish_authority(tmp_path):
    gateway, mount, _ = _gateway(tmp_path)
    framework_root = tmp_path / "site-packages" / "django" / "contrib" / "auth"
    framework_root.mkdir(parents=True)
    framework_app = SimpleNamespace(
        label="auth",
        name="django.contrib.auth",
        path=framework_root,
    )
    mount.apps = (*mount.apps, framework_app)
    gateway.ops = SimpleNamespace(
        records=lambda: (_operation(framework_app, "auth.list", mutates=False),)
    )

    assert derive_django_publications(gateway) == ()


def test_management_command_joins_owned_app_scope_by_django_registry(tmp_path, monkeypatch):
    gateway, mount, app = _gateway(tmp_path)
    gateway.ops = SimpleNamespace(
        records=lambda: (
            _operation(app, "widgets.list", mutates=False),
            _command(mount, "sync_widgets", mutates=True),
        )
    )
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {"sync_widgets": app.name},
    )

    scopes = {scope.name: scope for scope in derive_django_publications(gateway)}

    assert scopes["demo-widgets-read"].operations == frozenset({"widgets.list"})
    assert scopes["demo-widgets-write"].operations == frozenset(
        {"demo.sync_widgets"}
    )


def test_management_command_read_contract_stays_read_only(tmp_path, monkeypatch):
    gateway, mount, app = _gateway(tmp_path)
    gateway.ops = SimpleNamespace(
        records=lambda: (_command(mount, "inspect_widgets", mutates=False),)
    )
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {"inspect_widgets": app.name},
    )

    scopes = derive_django_publications(gateway)

    assert [scope.name for scope in scopes] == ["demo-widgets-read"]
    assert scopes[0].operations == frozenset({"demo.inspect_widgets"})


def test_management_command_without_owned_app_provenance_publishes_nothing(
    tmp_path, monkeypatch
):
    gateway, mount, _ = _gateway(tmp_path)
    gateway.ops = SimpleNamespace(
        records=lambda: (_command(mount, "migrate", mutates=True),)
    )
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {"migrate": "django.core"},
    )

    assert derive_django_publications(gateway) == ()


def test_collect_replaces_old_derived_scopes_but_preserves_manual_publications(
    tmp_path,
):
    gateway, _, app = _gateway(tmp_path)
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


def test_installed_app_without_operations_creates_no_scope(tmp_path):
    gateway, _, _ = _gateway(tmp_path)
    gateway.ops = SimpleNamespace(records=lambda: ())

    assert derive_django_publications(gateway) == ()
