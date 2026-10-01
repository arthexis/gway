from gway.config import project_scopes
from gway.security.defaults import converge_scope_registry
from gway.security.publication import PublishedScope, normalize_publications
from gway.security.scopes import ScopeRegistry


def test_pyproject_scopes_adapt_to_normalized_publications():
    document = {
        "tool": {
            "gway": {
                "scopes": {
                    "demo-read": {
                        "operations": ["demo.status"],
                        "environment": [],
                        "semantic_terms": ["Demo", "read"],
                    }
                }
            }
        }
    }

    publications = normalize_publications(project_scopes(document, source="demo"))

    assert publications == {
        "demo-read": PublishedScope(
            "demo-read",
            "demo",
            operations=frozenset({"demo.status"}),
            semantic_terms=frozenset({"demo", "read"}),
        )
    }


def test_ingester_can_publish_normalized_scope_directly(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope(
        "cards-read",
        "django:billing:cards",
        operations=frozenset({"cards.list"}),
        semantic_terms=frozenset({"cards", "read"}),
    )

    converge_scope_registry(registry, [publication])

    scope = registry.require("cards-read")
    assert scope.owner == "project:django:billing:cards"
    assert scope.operations == frozenset({"cards.list"})
    assert scope.semantic_terms == frozenset({"cards", "read"})


def test_publication_normalizes_terms_and_authority_sets():
    publication = PublishedScope(
        " Demo-Read ",
        " pyproject:demo ",
        operations=[" demo.status ", "demo.status"],
        environment=[" DEMO_URL ", "DEMO_URL"],
        semantic_terms=["Read", "DEMO", "demo"],
    )

    assert publication.name == "Demo-Read"
    assert publication.source == "pyproject:demo"
    assert publication.operations == frozenset({"demo.status"})
    assert publication.environment == frozenset({"DEMO_URL"})
    assert publication.semantic_terms == frozenset({"demo", "read"})


def test_publication_requires_source_before_durable_convergence(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope("demo-read", "", operations={"demo.status"})

    try:
        converge_scope_registry(registry, [publication])
    except ValueError as exc:
        assert "has no publisher source" in str(exc)
    else:
        raise AssertionError("source-less publication unexpectedly converged")


def test_conflicting_iterable_publications_fail_closed():
    publications = [
        PublishedScope("demo-read", "one", operations={"demo.one"}),
        PublishedScope("demo-read", "two", operations={"demo.two"}),
    ]

    try:
        normalize_publications(publications)
    except ValueError as exc:
        assert "Conflicting publications for scope demo-read" in str(exc)
    else:
        raise AssertionError("conflicting publications unexpectedly normalized")


def test_convergence_report_is_idempotent_and_retires_missing_publications(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")
    publication = PublishedScope(
        "demo-read",
        "demo",
        operations={"demo.status"},
    )

    first = converge_scope_registry(registry, [publication], report=True)
    assert "demo-read" in first["added"]
    assert first["updated"] == []

    second = converge_scope_registry(registry, [publication], report=True)
    assert second["added"] == []
    assert second["updated"] == []
    assert "demo-read" in second["unchanged"]

    retired = converge_scope_registry(registry, [], report=True)
    assert retired["retired"] == ["demo-read"]
    assert registry.get("demo-read") is None


def test_convergence_rolls_back_all_changes_when_owned_scope_conflicts(tmp_path):
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

    try:
        converge_scope_registry(registry, publications, report=True)
    except ValueError as exc:
        assert "owned by project:original" in str(exc)
    else:
        raise AssertionError("conflicting convergence unexpectedly succeeded")

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

    try:
        gateway("security scope converge")
    except ValueError as exc:
        assert "missing.operation" in str(exc)
    else:
        raise AssertionError("unsafe semantic read publication unexpectedly converged")

    assert not gateway.security_path.exists()
