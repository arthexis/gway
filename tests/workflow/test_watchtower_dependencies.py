from pathlib import Path

import pytest


pytestmark = pytest.mark.workflow

WORKFLOW = Path(".github/workflows/watchtower-dependencies.yml")
RESOLVER = Path(".github/scripts/watchtower_dependency.py")


def test_needs_watchtower_reconciler_parks_and_releases_auto_merge():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "needs-watchtower" in text
    assert "Watchtower-Depends-On" not in text  # parsing belongs to the resolver
    assert "--disable-auto" in text
    assert "--auto --squash" in text
    assert "repository_dispatch:" in text
    assert "watchtower-accepted" in text


def test_dependency_resolver_uses_certified_descendant_semantics():
    text = RESOLVER.read_text(encoding="utf-8")

    assert "Watchtower-Depends-On:" in text
    assert '"gway_sha" if repo == "arthexis/gway" else "arthexis_sha"' in text
    assert 'comparison.get("status") in {"identical", "ahead"}' in text
    assert "Watchtower dependency cycle" in text
