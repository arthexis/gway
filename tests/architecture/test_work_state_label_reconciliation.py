from pathlib import Path


def test_work_state_reconciliation_uses_newly_applied_label_as_authority() -> None:
    workflow = Path(".github/workflows/approved-auto-merge.yml").read_text(
        encoding="utf-8"
    )

    assert 'case "$label" in' in workflow
    assert "approved)" in workflow
    assert 'gh pr edit "$PR_NUMBER" --repo "$REPOSITORY" --remove-label in-progress' in workflow
    assert "in-progress)" in workflow
    assert 'gh pr edit "$PR_NUMBER" --repo "$REPOSITORY" --remove-label approved' in workflow
    assert "was newly approved; removing in-progress" in workflow
    assert "was newly marked in-progress; removing Approved" in workflow
