from pathlib import Path

from gway.checkpoint.chain import ChainContinuationCheckpoint
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.provenance import ContinuationPoint
from gway.registry import Registry
from gway.runtime import GwayRuntime
from gway.runtime_reload import create_reload_checkpoint


def test_create_reload_checkpoint_uses_v3_for_pending_chain(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(Project(name="demo", path=root, adapter_type="python", adapter_config={"module": "unused"}))
    runtime = GwayRuntime(Dispatcher(registry))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("reload - demo scalar\n", encoding="utf-8")
    point = ContinuationPoint(str(recipe), 1, 1, None, None)
    with runtime.frame_scope("recipe", recipe_path=str(recipe)):
        with runtime.frames.continuation_scope(point, context={}, provenance={}):
            with runtime.frame_scope("statement", tokens=("reload", "-", "demo", "scalar"), recipe_path=str(recipe), recipe_line=1):
                with runtime.frames.chain_continuation_scope(statement_tokens=("reload", "-", "demo", "scalar"), recipe_path=str(recipe), recipe_line=1) as state:
                    assert state is not None
                    state.active_stage_index = 1
                    checkpoint = create_reload_checkpoint(runtime, interactive=False)
    assert isinstance(checkpoint, ChainContinuationCheckpoint)
    assert checkpoint.pending_chains[0].active_stage_index == 1
