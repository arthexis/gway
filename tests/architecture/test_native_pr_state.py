from pathlib import Path


def test_premature_pr_drive_workflow_is_removed() -> None:
    # #1385 deliberately removed the Branch Update workflow because it invoked
    # the full Drive lifecycle state machine as a branch-refresh mechanism.
    # Drive will return as its own independently tested workflow when ready.
    assert not Path(".github/workflows/branch-update.yml").exists()


def test_native_auto_merge_guard_workflow_is_removed() -> None:
    assert not Path(
        ".github/workflows/native-auto-merge-guard.yml"
    ).exists()
