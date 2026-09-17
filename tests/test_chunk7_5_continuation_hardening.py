from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.checkpoint.chain import ChainContinuationCheckpoint
from gway.checkpoint.resume import ResumeError, resume_recipe
from gway.checkpoint.store import read_checkpoint
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime


class _ExecIntercept(BaseException):
    pass


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "chunk75-project"
    root.mkdir()
    (root / "chunk75_commands.py").write_text(
        """def produce() -> str:
    return "seed"


def tag(value: str) -> str:
    return value + ":tag"


def fail(value: str) -> str:
    raise RuntimeError("resumed parent tail failed: " + value)
""",
        encoding="utf-8",
    )
    sys.modules.pop("chunk75_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "chunk75_commands"},
        )
    )
    return Dispatcher(registry)


def _nested_recipes(
    tmp_path: Path,
    *,
    failing_root: bool = False,
) -> tuple[Path, Path, Path]:
    leaf = tmp_path / "leaf.rx"
    middle = tmp_path / "middle.rx"
    root = tmp_path / "root.rx"
    leaf.write_text("reload\ndemo produce\n", encoding="utf-8")
    middle.write_text(f"recipe {leaf} - demo tag\n", encoding="utf-8")
    tail = "fail" if failing_root else "tag"
    root.write_text(f"recipe {middle} - demo {tail}\n", encoding="utf-8")
    return root, middle, leaf


def _capture_checkpoint(
    dispatcher: Dispatcher,
    root: Path,
    monkeypatch,
    *,
    explain: bool = False,
) -> ChainContinuationCheckpoint:
    runtime = GwayRuntime(dispatcher)
    captured: dict[str, object] = {}

    def fake_execv(executable: str, argv: list[str]) -> None:
        captured["argv"] = list(argv)
        raise _ExecIntercept()

    monkeypatch.setattr("gway.runtime_reload.os.execv", fake_execv)
    if explain:
        with explain_scope(), pytest.raises(_ExecIntercept):
            runtime.execute(["recipe", str(root)])
    else:
        with pytest.raises(_ExecIntercept):
            runtime.execute(["recipe", str(root)])

    argv = captured["argv"]
    assert isinstance(argv, list)
    checkpoint = read_checkpoint(Path(argv[4]))
    assert isinstance(checkpoint, ChainContinuationCheckpoint)
    return checkpoint


def test_three_level_resume_unwinds_each_pending_parent_tail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    root, _, _ = _nested_recipes(tmp_path)
    checkpoint = _capture_checkpoint(dispatcher, root, monkeypatch)

    assert len(checkpoint.frames) == 3
    assert len(checkpoint.pending_chains) == 2

    runtime = GwayRuntime(dispatcher)
    result = resume_recipe(checkpoint, dispatcher, runtime=runtime)

    assert result == "seed:tag:tag"
    assert runtime.frames.active_chains == ()
    assert runtime.frames.active_continuations == ()
    assert runtime.frames.continuations == ()
    assert runtime.current_frame is None


def test_three_level_resume_explains_restored_stack_and_chain_unwind(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    root, middle, leaf = _nested_recipes(tmp_path)
    checkpoint = _capture_checkpoint(dispatcher, root, monkeypatch, explain=True)
    runtime = GwayRuntime(dispatcher)

    with explain_scope() as trace:
        assert resume_recipe(checkpoint, dispatcher, runtime=runtime) == "seed:tag:tag"

    restored_frames = [step for step in trace if step.kind == "resume.frame.restore"]
    assert [step.data["frame_id"] for step in restored_frames] == [
        frame.frame_id for frame in checkpoint.frames
    ]
    assert [step.data["recipe_path"] for step in restored_frames] == [
        str(root),
        str(middle),
        str(leaf),
    ]
    assert [step.data["parent_frame_id"] for step in restored_frames] == [
        None,
        checkpoint.frames[0].frame_id,
        checkpoint.frames[1].frame_id,
    ]

    restored_chains = [step for step in trace if step.kind == "resume.chain.restore"]
    assert len(restored_chains) == 2
    assert all(step.data["next_stage_index"] == 2 for step in restored_chains)
    assert [step.data["previous_result"] for step in restored_chains] == [
        "seed",
        "seed:tag",
    ]

    chain_results = [step for step in trace if step.kind == "resume.chain.result"]
    assert [step.data["result"] for step in chain_results] == [
        "seed:tag",
        "seed:tag:tag",
    ]
    assert chain_results[-1].data["provenance"]["operation"] == "demo"
    final_chain_index = max(
        index for index, step in enumerate(trace) if step.kind == "resume.chain.result"
    )
    assert final_chain_index > max(
        index for index, step in enumerate(trace) if step.kind == "resume.frame.restore"
    )
    assert final_chain_index > max(
        index for index, step in enumerate(trace) if step.kind == "resume.chain.restore"
    )


@pytest.mark.parametrize("changed_level", ["root", "middle", "leaf"])
def test_nested_resume_validates_every_recipe_before_execution(
    tmp_path: Path,
    monkeypatch,
    changed_level: str,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    root, middle, leaf = _nested_recipes(tmp_path)
    checkpoint = _capture_checkpoint(dispatcher, root, monkeypatch)
    paths = {"root": root, "middle": middle, "leaf": leaf}
    changed = paths[changed_level]
    changed.write_text(
        changed.read_text(encoding="utf-8") + "# changed\n",
        encoding="utf-8",
    )

    runtime = GwayRuntime(dispatcher)
    with pytest.raises(ResumeError, match="recipe changed since checkpoint was created"):
        resume_recipe(checkpoint, dispatcher, runtime=runtime)

    assert runtime.frames.active_chains == ()
    assert runtime.frames.active_continuations == ()
    assert runtime.current_frame is None


def test_restored_frame_ids_advance_fresh_allocation_without_collision() -> None:
    runtime = GwayRuntime()

    with runtime.frames.restored_scope(
        "frame-41",
        "recipe",
        expected_parent_id=None,
        recipe_path="restored.rx",
    ):
        pass

    with runtime.frame_scope("recipe", recipe_path="fresh.rx") as fresh:
        assert fresh.id == "frame-42"
        assert not runtime.frames.is_restored(fresh.id)

    assert runtime.frames.get("frame-41") is not None
    assert runtime.frames.get("frame-42") is not None


def test_resumed_parent_tail_failure_cleans_all_runtime_stacks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    root, _, _ = _nested_recipes(tmp_path, failing_root=True)
    checkpoint = _capture_checkpoint(dispatcher, root, monkeypatch)
    runtime = GwayRuntime(dispatcher)

    with pytest.raises(RuntimeError, match="resumed parent tail failed: seed:tag"):
        resume_recipe(checkpoint, dispatcher, runtime=runtime)

    assert runtime.frames.active_chains == ()
    assert runtime.frames.active_continuations == ()
    assert runtime.frames.continuations == ()
    assert runtime.current_frame is None
