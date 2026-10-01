from gway.security.defaults import converge_scope_registry
from gway.security.django_publication import (
    collect_django_publications,
    derive_django_publications,
)
from gway.security.publication import normalize_publications
from gway.security.scopes import ScopeRegistry


def test_lazy_django_ingestion_drives_scope_publication_and_convergence(
    gateway,
    django_mount,
    django_orm,
    django_management,
    tmp_path,
):
    Charger, manager = django_orm
    type(manager).filter.__gway_mutates__ = False
    django_management({"sync_energy": "energy"})
    django_mount(Charger, name="demo")

    # Merely mounting an app does not manufacture authority. The model surface
    # remains lazy until an operation is actually resolved and registered.
    assert derive_django_publications(gateway) == ()

    assert gateway("filter charger --site MTY") == {"site": "MTY"}

    scopes = {scope.name: scope for scope in derive_django_publications(gateway)}
    assert "demo-energy-read" in scopes
    assert "energy.charger.filter" in scopes["demo-energy-read"].operations
    assert scopes["demo-energy-read"].semantic_terms == frozenset(
        {"demo", "energy", "read"}
    )

    # Unknown manager/model callables remain conservatively mutating, so the
    # expanded surface also produces write authority without guessing names.
    assert "demo-energy-write" in scopes
    assert "energy.charger.create" in scopes["demo-energy-write"].operations

    collect_django_publications(gateway)
    publications = normalize_publications(gateway._published_scopes)
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    report = converge_scope_registry(registry, publications.values(), report=True)

    assert "demo-energy-read" in report["added"]
    assert "demo-energy-write" in report["added"]

    read_scope = registry.require("demo-energy-read")
    assert read_scope.owner == "project:django:demo:energy"
    assert read_scope.semantic_terms == frozenset({"demo", "energy", "read"})
    assert "energy.charger.filter" in read_scope.operations


def test_lazy_management_command_joins_owned_app_scope(
    gateway,
    django_mount,
    django_orm,
    django_management,
):
    Charger, _ = django_orm
    calls = django_management({"sync_energy": "energy"})
    django_mount(Charger, name="demo")

    assert gateway.ops.resolve("demo.sync_energy") is None
    assert gateway("sync energy demo --force") == {
        "command": "sync_energy",
        "args": (),
        "options": {"force": True},
    }
    assert calls == [("sync_energy", (), {"force": True})]

    scopes = {scope.name: scope for scope in derive_django_publications(gateway)}

    assert "demo-energy-write" in scopes
    assert "demo.sync_energy" in scopes["demo-energy-write"].operations
    assert scopes["demo-energy-write"].source == "django:demo:energy"
