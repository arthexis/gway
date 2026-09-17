from pathlib import Path

from gway.checkpoint import CheckpointFlags, recipe_identity
from gway.checkpoint.chain import ChainContinuationCheckpoint, PendingChainCheckpoint, PendingStageCheckpoint
from gway.checkpoint.stack import ContinuationFrameCheckpoint
from gway.checkpoint.store import read_checkpoint, write_checkpoint_atomic
from gway.provenance import ContinuationPoint
from gway.stage import StageKind


def test_checkpoint_store_round_trips_v3(tmp_path: Path) -> None:
    recipe = tmp_path / "chain.rx"
    recipe.write_text("reload - demo scalar\n", encoding="utf-8")
    point = ContinuationPoint(str(recipe), 1, 1, None, None)
    frame = ContinuationFrameCheckpoint(
        frame_id="frame-1",
        parent_frame_id=None,
        recipe=recipe_identity(recipe),
        continuation=point,
    )
    pending = PendingChainCheckpoint(
        frame_id="frame-1",
        recipe_path=str(recipe),
        recipe_line=1,
        statement_tokens=("reload", "-", "demo", "scalar"),
        active_stage_index=1,
        remaining_stages=(PendingStageCheckpoint(("demo", "scalar"), StageKind.COMMAND),),
    )
    checkpoint = ChainContinuationCheckpoint(
        frames=(frame,), pending_chains=(pending,), flags=CheckpointFlags()
    )
    path = write_checkpoint_atomic(checkpoint, tmp_path / "data")
    restored = read_checkpoint(path)
    assert isinstance(restored, ChainContinuationCheckpoint)
    assert restored == checkpoint
