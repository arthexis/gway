from pathlib import Path

import pytest

from gway.checkpoint import CheckpointFlags, recipe_identity
from gway.checkpoint.chain import ChainContinuationCheckpoint, PendingChainCheckpoint, PendingStageCheckpoint
from gway.checkpoint.resume import ResumeError, resume_recipe
from gway.checkpoint.stack import ContinuationFrameCheckpoint
from gway.dispatcher import Dispatcher
from gway.provenance import ContinuationPoint
from gway.stage import StageKind


def test_v3_resume_rejects_changed_recipe_before_execution(tmp_path: Path) -> None:
    recipe = tmp_path / "changed.rx"
    recipe.write_text("reload - demo scalar\n", encoding="utf-8")
    frame = ContinuationFrameCheckpoint(
        frame_id="frame-1",
        parent_frame_id=None,
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(str(recipe), 1, 1, None, None),
    )
    pending = PendingChainCheckpoint(
        frame_id="frame-1",
        recipe_path=str(recipe),
        recipe_line=1,
        statement_tokens=("reload", "-", "demo", "scalar"),
        active_stage_index=1,
        remaining_stages=(PendingStageCheckpoint(("demo", "scalar"), StageKind.COMMAND),),
    )
    checkpoint = ChainContinuationCheckpoint(frames=(frame,), pending_chains=(pending,), flags=CheckpointFlags())
    recipe.write_text("reload - demo changed\n", encoding="utf-8")
    with pytest.raises(ResumeError, match="recipe changed since checkpoint was created"):
        resume_recipe(checkpoint, Dispatcher())
