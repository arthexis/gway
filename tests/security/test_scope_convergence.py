import pytest

from gway.security.defaults import CORE_SCOPE_DEFINITIONS, converge_scope_registry
from gway.security.scopes import ScopeRegistry


def test_bundled_convergence_creates_owned_scopes_and_preserves_custom_scope(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("custom-ops", operations={"demo.status"})

    report = converge_scope_registry(registry, report=True)

    assert set(report["added"]) == set(CORE_SCOPE_DEFINITIONS)
    custom = registry.require("custom-ops")
    assert custom.owner is None
    assert custom.operations == frozenset({"demo.status"})
    for name, definition in CORE_SCOPE_DEFINITIONS.items():
        scope = registry.require(name)
        assert scope.owner == "gway"
        assert scope.operations == definition["operations"]
        assert scope.environment == definition["environment"]


def test_bundled_convergence_is_idempotent_for_owned_policy(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    first = converge_scope_registry(registry, report=True)
    second = converge_scope_registry(registry, report=True)

    assert set(first["added"]) == set(CORE_SCOPE_DEFINITIONS)
    assert second["added"] == []
    assert second["updated"] == []
    assert second["retired"] == []
    assert set(second["unchanged"]) == set(CORE_SCOPE_DEFINITIONS)


def test_matching_unowned_legacy_bundle_is_adopted_without_authority_change(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    definition = CORE_SCOPE_DEFINITIONS["operator-read"]
    registry.replace(
        "operator-read",
        operations=definition["operations"],
        environment=definition["environment"],
    )
    before = registry.require("operator-read")

    report = converge_scope_registry(registry, report=True)
    after = registry.require("operator-read")

    assert before.owner is None
    assert after.owner == "gway"
    assert after.operations == before.operations
    assert after.environment == before.environment
    assert "operator-read" in report["updated"]


def test_differing_unowned_same_name_scope_is_not_claimed_or_overwritten(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace("operator-read", operations={"custom.status"})
    before = registry.all()

    with pytest.raises(ValueError, match="user-managed and differs"):
        converge_scope_registry(registry, report=True)

    assert registry.all() == before
    scope = registry.require("operator-read")
    assert scope.owner is None
    assert scope.operations == frozenset({"custom.status"})


def test_foreign_owned_bundle_conflict_rolls_back_entire_convergence(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace_owned(
        "operator-write",
        owner="extension:demo",
        operations={"demo.write"},
    )
    registry.replace("custom-ops", operations={"demo.status"})
    before = registry.all()

    with pytest.raises(ValueError, match="owned by extension:demo"):
        converge_scope_registry(registry, report=True)

    assert registry.all() == before
    assert registry.get("full-access") is None


def test_gway_owned_bundle_updates_deterministically(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    converge_scope_registry(registry)
    registry.replace_owned(
        "operator-read",
        owner="gway",
        operations={"obsolete.operation"},
    )

    report = converge_scope_registry(registry, report=True)
    scope = registry.require("operator-read")

    assert scope.owner == "gway"
    assert scope.operations == CORE_SCOPE_DEFINITIONS["operator-read"]["operations"]
    assert "operator-read" in report["updated"]


def test_generated_project_scopes_are_retired_without_touching_user_scopes(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace_owned(
        "legacy-project-read",
        owner="project:django:demo",
        operations={"demo.status"},
    )
    registry.replace("custom-ops", operations={"custom.status"})

    report = converge_scope_registry(registry, report=True)

    assert report["retired"] == ["legacy-project-read"]
    assert registry.get("legacy-project-read") is None
    assert registry.require("custom-ops").operations == frozenset({"custom.status"})
