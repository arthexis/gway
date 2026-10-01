from gway.security.defaults import converge_scope_registry
from gway.security.django_publication import collect_django_publications
from gway.security.publication import normalize_publications
from gway.security.scopes import ScopeRegistry


def _publications(gateway):
    collect_django_publications(gateway)
    return normalize_publications(gateway._published_scopes)


def test_django_authority_derives_and_converges_as_one_contract(
    django_scope,
    tmp_path,
):
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
        django_scope.operation(django_scope.app, "widgets.create", mutates=True),
    )
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    report = converge_scope_registry(
        registry,
        _publications(django_scope.gateway),
        report=True,
    )

    assert {"demo-widgets-read", "demo-widgets-write"} <= set(report["added"])

    read = registry.require("demo-widgets-read")
    write = registry.require("demo-widgets-write")
    assert read.owner == "project:django:demo:widgets"
    assert read.semantic_terms == frozenset({"demo", "widgets", "read"})
    assert read.operations == frozenset({"widgets.list"})
    assert write.owner == "project:django:demo:widgets"
    assert write.semantic_terms == frozenset({"demo", "widgets", "write"})
    assert write.operations == frozenset({"widgets.create"})


def test_reconvergence_updates_and_retires_changed_django_authority(
    django_scope,
    tmp_path,
):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
        django_scope.operation(django_scope.app, "widgets.create", mutates=True),
    )
    converge_scope_registry(registry, _publications(django_scope.gateway), report=True)

    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.detail", mutates=False),
    )
    report = converge_scope_registry(
        registry,
        _publications(django_scope.gateway),
        report=True,
    )

    assert "demo-widgets-read" in report["updated"]
    assert "demo-widgets-write" in report["retired"]
    assert registry.require("demo-widgets-read").operations == frozenset(
        {"widgets.detail"}
    )
    assert registry.get("demo-widgets-write") is None
