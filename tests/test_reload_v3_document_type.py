from pathlib import Path

from gway.checkpoint import CheckpointFlags, recipe_identity
from gway.checkpoint_chain import ChainContinuationCheckpoint, PendingChainCheckpoint, PendingStageCheckpoint
from gway.checkpoint_stack import ContinuationFrameCheckpoint
from gway.provenance import ContinuationPoint
from gway.stage import StageKind


def test_v3_preserves_runtime_flags(tmp_path: Path) -> None:
    recipe = tmp_path / "flags.rx"
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
    flags = CheckpointFlags(interactive=True, explain=True, output_mode="json")
    checkpoint = ChainContinuationCheckpoint(frames=(frame,), pending_chains=(pending,), flags=flags)
    restored = ChainContinuationCheckpoint.from_json(checkpoint.to_json())
    assert restored.flags == flags
