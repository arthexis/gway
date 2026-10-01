from types import SimpleNamespace

import pytest

import gway.security.django_publication as publication
from gway.ingestion.base import IngestedObject
from gway.ingestion.django import DjangoProject
from gway.security.django_publication import (
    collect_django_publications,
    derive_django_publications,
)


class DjangoScopeHarness:
    """Build minimal owned Django surfaces for scope-publication contracts."""

    def __init__(self, tmp_path, *, product="demo", app_label="widgets"):
        root = tmp_path / product
        root.mkdir()
        self.app = self._app(root, product, app_label)
        self.mount = DjangoProject(
            root=root,
            settings=None,
            name=product,
            registry=SimpleNamespace(),
            apps=(self.app,),
        )
        self.gateway = SimpleNamespace(
            _ingested={1: IngestedObject(value=self.mount)},
            _published_scopes={},
            ops=SimpleNamespace(records=lambda: ()),
        )

    @staticmethod
    def _app(root, product, label):
        path = root / label
        path.mkdir(parents=True)
        return SimpleNamespace(
            label=label,
            name=f"{product}.{label}",
            path=path,
        )

    def external_app(self, root, *, label="auth", name="django.contrib.auth"):
        path = root / label
        path.mkdir(parents=True)
        app = SimpleNamespace(label=label, name=name, path=path)
        self.mount.apps = (*self.mount.apps, app)
        return app

    @staticmethod
    def operation(app, name, *, mutates):
        meta = SimpleNamespace(app_config=app)
        model = type("Model", (), {"_meta": meta})

        def invoke():
            return None

        invoke.__gway_source__ = model
        invoke.__gway_source_kind__ = "django-model"
        invoke.mutates = mutates
        return SimpleNamespace(name=name, callable=invoke)

    def command(self, name, *, mutates):
        def invoke():
            return None

        invoke.__gway_source__ = self.mount
        invoke.__gway_source_kind__ = "django-command"
        invoke.__gway_metadata__ = {
            "project": self.mount.name,
            "command": name,
            "settings": self.mount.settings,
        }
        invoke.mutates = mutates
        return SimpleNamespace(name=f"{self.mount.name}.{name}", callable=invoke)

    def records(self, *records):
        self.gateway.ops = SimpleNamespace(records=lambda: records)
        return self

    def scopes(self):
        return {
            scope.name: scope for scope in derive_django_publications(self.gateway)
        }


@pytest.fixture
def django_scope(tmp_path):
    return DjangoScopeHarness(tmp_path)


@pytest.mark.parametrize("app_label", ["widgets", "gadgets"])
def test_scope_identity_is_derived_from_product_and_app(tmp_path, app_label):
    harness = DjangoScopeHarness(tmp_path, app_label=app_label)
    harness.records(
        harness.operation(harness.app, f"{app_label}.list", mutates=False),
    )

    scope = harness.scopes()[f"demo-{app_label}-read"]

    assert scope.semantic_terms == frozenset({"demo", app_label, "read"})
    assert scope.source == f"django:demo:{app_label}"


def test_mutation_contract_partitions_operations_into_read_and_write(django_scope):
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
        django_scope.operation(django_scope.app, "widgets.create", mutates=True),
    )

    scopes = django_scope.scopes()

    assert set(scopes) == {"demo-widgets-read", "demo-widgets-write"}
    assert scopes["demo-widgets-read"].operations == frozenset({"widgets.list"})
    assert scopes["demo-widgets-write"].operations == frozenset({"widgets.create"})


def test_app_outside_project_root_does_not_publish_authority(django_scope, tmp_path):
    framework_app = django_scope.external_app(
        tmp_path / "site-packages" / "django" / "contrib"
    )
    django_scope.records(
        django_scope.operation(framework_app, "auth.list", mutates=False),
    )

    assert django_scope.scopes() == {}


@pytest.mark.parametrize(
    ("command", "mutates", "leaf"),
    [
        ("inspect_widgets", False, "demo-widgets-read"),
        ("sync_widgets", True, "demo-widgets-write"),
    ],
)
def test_management_command_uses_owned_app_and_mutation_contract(
    django_scope,
    monkeypatch,
    command,
    mutates,
    leaf,
):
    django_scope.records(django_scope.command(command, mutates=mutates))
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {command: django_scope.app.name},
    )

    scopes = django_scope.scopes()

    assert list(scopes) == [leaf]
    assert scopes[leaf].operations == frozenset({f"demo.{command}"})


def test_management_command_without_owned_app_provenance_publishes_nothing(
    django_scope,
    monkeypatch,
):
    django_scope.records(django_scope.command("migrate", mutates=True))
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {"migrate": "django.core"},
    )

    assert django_scope.scopes() == {}


def test_collect_retires_stale_django_scopes_and_preserves_manual_publications(
    django_scope,
):
    django_scope.gateway._published_scopes = {
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
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
    )

    published = collect_django_publications(django_scope.gateway)

    assert set(published) == {"manual-read", "demo-widgets-read"}
    assert published["demo-widgets-read"]["semantic_terms"] == frozenset(
        {"demo", "widgets", "read"}
    )


@pytest.mark.parametrize("has_registry", [False, True])
def test_no_discovered_operations_publish_no_authority(tmp_path, has_registry):
    harness = DjangoScopeHarness(tmp_path)
    if not has_registry:
        del harness.gateway.ops

    assert derive_django_publications(harness.gateway) == ()
