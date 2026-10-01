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


def test_branch_update_delegates_pr_policy_to_drive() -> None:
    workflow = Path(
        ".github/workflows/branch-update.yml"
    ).read_text(encoding="utf-8")

    assert 'python -m gway github drive "$REPOSITORY" "$pr_number"' in workflow
    assert "GWAY_GITHUB_TOKEN" in workflow
    assert "drive-results" in workflow
    assert "actions/upload-artifact@v6" in workflow

    # The workflow may select targets, but lifecycle policy belongs to Drive.
    assert "behind_by" not in workflow
    assert "expected_head_sha" not in workflow
    assert "/update-branch" not in workflow
    assert '== "in-progress"' not in workflow
    assert '== "approved"' not in workflow
    assert "on-hold" not in workflow
    assert "on hold" not in workflow
