from pathlib import Path

import pytest


pytestmark = pytest.mark.workflow

WORKFLOW = Path(".github/workflows/release.yml")


def test_release_publishes_only_watchtower_certified_revision():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "deployed_sha:" in text
    assert "companion_sha:" in text
    assert "watchtower_run:" in text
    assert 'OWN_FIELD="gway_sha" COMPANION_FIELD="arthexis_sha"' in text
    assert "Release blocked: supplied certification does not match" in text
    assert 'ref: ${{ inputs.deployed_sha }}' in text
    assert 'test "$(git rev-parse HEAD)" = "$DEPLOYED_SHA"' in text


def test_release_reconciles_missing_pypi_version_instead_of_bootstrap_fallback():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Reconcile deployed SHA on PyPI" in text
    assert 'url = f"https://pypi.org/pypi/{package}/{version}/json"' in text
    assert 'state = "missing"' in text
    assert 'state = "matching"' in text
    assert "Release blocked: PyPI already contains this version with" in text
    assert "if: steps.pypi.outputs.state == 'missing'" in text
    assert "pypa/gh-action-pypi-publish@release/v1" in text
    assert "attestations: true" in text
    assert "Verify PyPI release artifacts" in text


def test_release_requires_explicit_release_intent():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'label.get("name") == "release"' in text
    assert 'manifest.get("release_intent") == "manual"' in text
    assert 'manifest.get("stages") == ["0-gway", "1-arthexis", "2-remote"]' in text
    assert "Release blocked: no PR release label or certified manual" in text
