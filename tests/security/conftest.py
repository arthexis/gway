from types import SimpleNamespace

import pytest

from gway.ingestion.django import DjangoProject
from gway.security.django_publication import derive_django_publications


class DjangoScopeHarness:
    UNSET = object()

    def __init__(self, tmp_path, *, app_label="widgets"):
        self.root = tmp_path / "demo"
        self.root.mkdir()
        app_path = self.root / app_label
        app_path.mkdir()
        self.app = SimpleNamespace(
            label=app_label,
            name=app_label,
            path=app_path,
        )
        self.mount = DjangoProject(
            root=self.root,
            settings=None,
            name="demo",
            registry=SimpleNamespace(),
            apps=(self.app,),
        )
        self._records = []
        self.gateway = SimpleNamespace(
            ops=SimpleNamespace(records=lambda: tuple(self._records)),
            _django_projects={"demo": self.mount},
            _published_scopes={},
        )

    def external_app(self, path, *, label="external", name="external"):
        return SimpleNamespace(label=label, name=name, path=path)

    def operation(self, app, name, *, mutates=UNSET, kind="django-model"):
        model = type("Model", (), {})
        model._meta = SimpleNamespace(app_config=app)

        def callable_():
            return None

        callable_.__gway_source__ = SimpleNamespace(model=model)
        callable_.__gway_source_kind__ = kind
        if mutates is not self.UNSET:
            callable_.mutates = mutates
        return SimpleNamespace(name=name, callable=callable_)

    def command(self, command, *, mutates=UNSET):
        def callable_():
            return None

        callable_.__gway_source__ = self.mount
        callable_.__gway_source_kind__ = "django-command"
        callable_.__gway_metadata__ = {"command": command}
        if mutates is not self.UNSET:
            callable_.mutates = mutates
        return SimpleNamespace(name=f"demo.{command}", callable=callable_)

    def records(self, *records):
        self._records[:] = records
        return self

    def scopes(self):
        return {scope.name: scope for scope in derive_django_publications(self.gateway)}


@pytest.fixture
def django_scope_factory(tmp_path_factory):
    def factory(*, app_label="widgets"):
        return DjangoScopeHarness(tmp_path_factory.mktemp("django-scope"), app_label=app_label)

    factory.UNSET = DjangoScopeHarness.UNSET
    return factory


@pytest.fixture
def django_scope(django_scope_factory):
    return django_scope_factory()
