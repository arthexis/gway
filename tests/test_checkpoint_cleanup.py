from __future__ import annotations

from pathlib import Path

from gway import bootstrap
from gway.checkpoint import CheckpointError, CheckpointFlags
from gway.checkpoint import resume as checkpoint_resume
from gway.checkpoint import store as checkpoint_store
from gway import runtime as runtime_module


class _Runtime:
    def __init__(self) -> None:
        self.dispatcher = object()
        self.output_mode = None


def test_remove_checkpoint_distinguishes_post_unlink_sync_failure(
    tmp_path: Path, monkeypatch
) -> None:
    checkpoint = tmp_path / "claimed.json"
    checkpoint.write_text("checkpoint", encoding="utf-8")

    def fail_sync(directory: Path) -> None:
        raise CheckpointError(f"cannot sync {directory}")

    monkeypatch.setattr(checkpoint_store, "_sync_directory", fail_sync)

    try:
        checkpoint_store.remove_checkpoint(checkpoint)
    except checkpoint_store.CheckpointCleanupError as exc:
        assert "checkpoint was consumed" in str(exc)
    else:
        raise AssertionError("expected post-consumption cleanup failure")

    assert not checkpoint.exists()


def test_internal_resume_does_not_restore_consumed_checkpoint_on_cleanup_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    original = tmp_path / "checkpoint.json"
    claimed = tmp_path / ".checkpoint.in-progress"
    claimed.write_text("checkpoint", encoding="utf-8")
    checkpoint = type("Checkpoint", (), {"flags": CheckpointFlags()})()
    restored: list[tuple[object, object]] = []

    monkeypatch.setattr(checkpoint_store, "claim_checkpoint", lambda path: claimed)
    monkeypatch.setattr(checkpoint_store, "read_checkpoint", lambda path: checkpoint)
    monkeypatch.setattr(checkpoint_resume, "resume_recipe", lambda *args, **kwargs: "done")
    monkeypatch.setattr(runtime_module, "GwayRuntime", _Runtime)

    def remove_then_fail(path: str | Path) -> None:
        Path(path).unlink()
        raise checkpoint_store.CheckpointCleanupError("directory sync failed")

    monkeypatch.setattr(checkpoint_store, "remove_checkpoint", remove_then_fail)
    monkeypatch.setattr(
        checkpoint_store,
        "restore_checkpoint",
        lambda claimed_path, original_path: restored.append((claimed_path, original_path)),
    )

    assert bootstrap._run_internal_resume(["--resume", str(original)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "done"
    assert "warning: directory sync failed" in captured.err
    assert restored == []
    assert not claimed.exists()
