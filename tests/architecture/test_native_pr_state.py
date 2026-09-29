from pathlib import Path


def test_native_auto_merge_guard_uses_github_state_not_work_labels() -> None:
    workflow = Path(
        ".github/workflows/native-auto-merge-guard.yml"
    ).read_text(encoding="utf-8")

    assert "Native Auto-Merge Guard" in workflow
    assert "converted_to_draft" in workflow
    assert '"on-hold"' in workflow
    assert '"on hold"' in workflow
    assert "gh pr merge" in workflow
    assert "--disable-auto" in workflow
    assert '== "approved"' not in workflow
    assert '== "in-progress"' not in workflow
    assert "remove-label approved" not in workflow
    assert "remove-label in-progress" not in workflow


def test_branch_update_does_not_use_pr_work_state_as_a_lock() -> None:
    workflow = Path(
        ".github/workflows/approved-branch-update.yml"
    ).read_text(encoding="utf-8")

    assert "expected_head_sha=$head_sha" in workflow
    assert '== "in-progress"' not in workflow
    assert '== "approved"' not in workflow
    assert "labels[]=in-progress" not in workflow
    assert "remove-label in-progress" not in workflow
