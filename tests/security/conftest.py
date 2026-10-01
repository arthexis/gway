from types import SimpleNamespace

import pytest

from gway.ingestion.base import IngestedObject
from gway.ingestion.django import DjangoProject
from gway.security.django_publication import derive_django_publications


UNSET = object()


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
    def operation(app, name, *, mutates=UNSET, kind="django-model"):
        meta = SimpleNamespace(app_config=app)
        model = type("Model", (), {"_meta": meta})

        def invoke():
            return None

        invoke.__gway_source__ = model
        invoke.__gway_source_kind__ = kind
        if mutates is not UNSET:
            invoke.mutates = mutates
        return SimpleNamespace(name=name, callable=invoke)

    def command(self, name, *, mutates=UNSET):
        def invoke():
            return None

        invoke.__gway_source__ = self.mount
        invoke.__gway_source_kind__ = "django-command"
        invoke.__gway_metadata__ = {
            "project": self.mount.name,
            "command": name,
            "settings": self.mount.settings,
        }
        if mutates is not UNSET:
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
def django_scope_factory(tmp_path):
    def build(*, product="demo", app_label="widgets"):
        return DjangoScopeHarness(tmp_path, product=product, app_label=app_label)

    build.UNSET = UNSET
    return build


@pytest.fixture
def django_scope(django_scope_factory):
    return django_scope_factory()
