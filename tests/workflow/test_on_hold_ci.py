from pathlib import Path

import pytest


pytestmark = pytest.mark.workflow

CORE_WORKFLOWS = {
    "package.yml": 1,
    "quality.yml": 1,
    "secret-scan.yml": 1,
    "python-compatibility.yml": 3,
}

ON_HOLD_GUARD = (
    "github.event.action != 'labeled' || "
    "(github.event.label.name != 'on-hold' && "
    "github.event.label.name != 'on hold')"
)


@pytest.mark.parametrize(("workflow", "expected_guards"), CORE_WORKFLOWS.items())
def test_putting_pr_on_hold_skips_core_ci(workflow: str, expected_guards: int) -> None:
    text = (Path(".github/workflows") / workflow).read_text(encoding="utf-8")

    assert "labeled" in text
    assert text.count(ON_HOLD_GUARD) == expected_guards
