import pytest

from gway.config import project_scopes
from gway.security.publication import PublishedScope, normalize_publications


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


def test_publication_normalizes_identity_authority_and_terms():
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


def test_conflicting_iterable_publications_fail_closed():
    publications = [
        PublishedScope("demo-read", "one", operations={"demo.one"}),
        PublishedScope("demo-read", "two", operations={"demo.two"}),
    ]

    with pytest.raises(ValueError, match="Conflicting publications for scope demo-read"):
        normalize_publications(publications)
