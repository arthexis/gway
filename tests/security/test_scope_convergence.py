import pytest

from gway.security.defaults import converge_scope_registry
from gway.security.publication import PublishedScope
from gway.security.scopes import ScopeRegistry


def test_ingester_publication_persists_authority_and_provenance(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope(
        "cards-read",
        "django:billing:cards",
        operations={"cards.list"},
        semantic_terms={"cards", "read"},
    )

    converge_scope_registry(registry, [publication])

    scope = registry.require("cards-read")
    assert scope.owner == "project:django:billing:cards"
    assert scope.operations == frozenset({"cards.list"})
    assert scope.semantic_terms == frozenset({"cards", "read"})


def test_convergence_requires_publisher_provenance(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope("demo-read", "", operations={"demo.status"})

    with pytest.raises(ValueError, match="has no publisher source"):
        converge_scope_registry(registry, [publication])


def test_convergence_report_is_idempotent_and_retires_missing_publications(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope("demo-read", "demo", operations={"demo.status"})

    first = converge_scope_registry(registry, [publication], report=True)
    second = converge_scope_registry(registry, [publication], report=True)
    retired = converge_scope_registry(registry, [], report=True)

    assert "demo-read" in first["added"]
    assert first["updated"] == []
    assert second["added"] == []
    assert second["updated"] == []
    assert "demo-read" in second["unchanged"]
    assert retired["retired"] == ["demo-read"]
    assert registry.get("demo-read") is None


def test_convergence_rolls_back_all_changes_on_ownership_conflict(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    registry.replace_owned(
        "z-conflict",
        owner="project:original",
        operations={"old.operation"},
    )
    before = registry.all()
    publications = [
        PublishedScope("a-new", "demo", operations={"new.operation"}),
        PublishedScope("z-conflict", "demo", operations={"replacement.operation"}),
    ]

    with pytest.raises(ValueError, match="owned by project:original"):
        converge_scope_registry(registry, publications, report=True)

    assert registry.all() == before


def test_scope_converge_operation_validates_before_writing(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    gateway._published_scopes = {
        "demo-read": PublishedScope(
            "demo-read",
            "demo",
            operations={"missing.operation"},
            semantic_terms={"demo", "read"},
        )
    }

    with pytest.raises(ValueError, match="missing.operation"):
        gateway("security scope converge")

    assert not gateway.security_path.exists()
