from pathlib import Path


def test_pr_drive_workflow_owns_pr_lifecycle_triggers() -> None:
    workflow = Path(
        ".github/workflows/branch-update.yml"
    ).read_text(encoding="utf-8")

    assert 'python -m gway github drive "$REPOSITORY" "$pr_number"' in workflow
    assert "GWAY_GITHUB_TOKEN" in workflow
    assert "drive-results" in workflow
    assert "actions/upload-artifact@v6" in workflow

    # The consolidated Drive consumer covers the PR-local state transitions that
    # used to require a separate native-auto-merge guard workflow.
    assert "labeled" in workflow
    assert "unlabeled" in workflow
    assert "converted_to_draft" in workflow
    assert "ready_for_review" in workflow
    assert "synchronize" in workflow

    # The workflow may select targets, but lifecycle policy belongs to Drive.
    assert "behind_by" not in workflow
    assert "expected_head_sha" not in workflow
    assert "/update-branch" not in workflow
    assert "--disable-auto" not in workflow
    assert "auto_merge" not in workflow
    assert '== "in-progress"' not in workflow
    assert '== "approved"' not in workflow
    assert "on-hold" not in workflow
    assert "on hold" not in workflow


def test_native_auto_merge_guard_workflow_is_removed() -> None:
    assert not Path(
        ".github/workflows/native-auto-merge-guard.yml"
    ).exists()
