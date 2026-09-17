from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gway import bootstrap
from gway.checkpoint import CheckpointError, CheckpointFlags, ResumeCheckpoint, recipe_identity
from gway.checkpoint import resume as resume_module
from gway.checkpoint.store import checkpoint_directory, write_checkpoint_atomic
from gway.provenance import ContinuationPoint


def _checkpoint(recipe: Path) -> ResumeCheckpoint:
    return ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(
            recipe_path=str(recipe),
            statement_index=1,
            line=1,
            next_statement_index=2,
            next_line=2,
        ),
        flags=CheckpointFlags(),
    )


def test_resume_interrupt_restores_claimed_checkpoint(tmp_path: Path, monkeypatch) -> None:
    recipe = tmp_path / "interrupt.rx"
    recipe.write_text("first\nsecond\n", encoding="utf-8")
    checkpoint_path = write_checkpoint_atomic(_checkpoint(recipe), tmp_path / "data")

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(resume_module, "resume_recipe", interrupt)
    monkeypatch.setattr(
        "gway.runtime.GwayRuntime",
        lambda: SimpleNamespace(dispatcher=object(), output_mode=None),
    )

    with pytest.raises(KeyboardInterrupt):
        bootstrap._run_internal_resume(["--resume", str(checkpoint_path)])

    assert checkpoint_path.exists()
    assert not list(checkpoint_path.parent.glob("*.in-progress"))


def test_post_rename_sync_failure_removes_final_checkpoint(tmp_path: Path, monkeypatch) -> None:
    recipe = tmp_path / "sync-failure.rx"
    recipe.write_text("first\nsecond\n", encoding="utf-8")
    data_dir = tmp_path / "data"

    def fail_sync(_directory: Path) -> None:
        raise CheckpointError("directory sync failed")

    monkeypatch.setattr("gway.checkpoint.store._sync_directory", fail_sync)

    with pytest.raises(CheckpointError, match="directory sync failed"):
        write_checkpoint_atomic(_checkpoint(recipe), data_dir)

    directory = checkpoint_directory(data_dir)
    assert not list(directory.glob("*.json"))
    assert not list(directory.glob("*.tmp"))
