from pathlib import Path

import pytest


pytestmark = pytest.mark.workflow

CORE_WORKFLOWS = (
    "package.yml",
    "quality.yml",
    "secret-scan.yml",
    "python-compatibility.yml",
)


@pytest.mark.parametrize("workflow", CORE_WORKFLOWS)
def test_core_ci_does_not_subscribe_to_generic_label_changes(workflow: str) -> None:
    text = (Path(".github/workflows") / workflow).read_text(encoding="utf-8")

    assert "types: [opened, synchronize, reopened]" in text
    assert "labeled" not in text
    assert "unlabeled" not in text


def test_ci_label_dispatch_handles_hold_transitions_without_creating_hold_checks() -> None:
    text = Path(".github/workflows/ci-label-dispatch.yml").read_text(encoding="utf-8")

    assert "types: [labeled, unlabeled]" in text
    assert 'workflow|integration|version-only|on-hold|"on hold"' in text
    assert (
        'if [[ "$ACTION" == "labeled" && '
        '( "$label" == "on-hold" || "$label" == "on hold" ) ]]'
    ) in text
    assert "CI dispatch is unnecessary" in text
    assert "base_ref=\"$(jq -r '.base.ref' <<< \"$pr_json\")\"" in text
    assert '--ref "$base_ref"' in text


def test_ci_label_dispatch_ignores_ordinary_state_labels() -> None:
    text = Path(".github/workflows/ci-label-dispatch.yml").read_text(encoding="utf-8")

    assert "Label '$CHANGED_LABEL' does not affect CI" in text
    assert '== "approved"' not in text
    assert '== "in-progress"' not in text
    assert "remove-label approved" not in text
    assert "remove-label in-progress" not in text
