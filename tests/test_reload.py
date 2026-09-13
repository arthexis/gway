from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway import bootstrap
from gway.checkpoint import CheckpointFlags, ResumeCheckpoint, recipe_identity
from gway.checkpoint_store import read_checkpoint, write_checkpoint_atomic
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.provenance import ContinuationPoint
from gway.registry import Registry
from gway.runtime import GwayRuntime
from gway.runtime_reload import ReloadError


class _ExecIntercept(BaseException):
    pass


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "reload-project"
    root.mkdir()
    (root / "reload_commands.py").write_text(
        """def produce() -> dict[str, str]:
    return {"device": "gway-004"}


def consume(*, device: str) -> str:
    return device
""",
        encoding="utf-8",
    )
    sys.modules.pop("reload_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "reload_commands"},
        )
    )
    return Dispatcher(registry)


def _resume_checkpoint(recipe: Path) -> ResumeCheckpoint:
    return ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(str(recipe), 1, 1, 2, 2),
        context={"device": "gway-004", "result": {"device": "gway-004"}},
        has_previous_result=True,
        previous_result={"device": "gway-004"},
        flags=CheckpointFlags(),
    )


def test_reload_operation_persists_state_before_exec(tmp_path: Path, monkeypatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    runtime.output_mode = "json"
    recipe = tmp_path / "reload.rx"
    recipe.write_text("demo produce\nreload\ndemo consume\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_execv(executable: str, argv: list[str]) -> None:
        captured["executable"] = executable
        captured["argv"] = list(argv)
        raise _ExecIntercept()

    monkeypatch.setattr("gway.runtime_reload.os.execv", fake_execv)

    with explain_scope() as trace, pytest.raises(_ExecIntercept):
        runtime.execute(["recipe", str(recipe)], interactive=True)

    argv = captured["argv"]
    assert isinstance(argv, list)
    assert captured["executable"] == sys.executable
    assert argv[:4] == [sys.executable, "-m", "gway", "--resume"]
    checkpoint_path = Path(argv[4])
    assert checkpoint_path.exists()
    assert not list(checkpoint_path.parent.glob("*.tmp"))

    checkpoint = read_checkpoint(checkpoint_path)
    assert checkpoint.continuation == ContinuationPoint(str(recipe), 2, 2, 3, 3)
    assert checkpoint.context["device"] == "gway-004"
    assert checkpoint.context["result"] == {"device": "gway-004"}
    assert checkpoint.has_previous_result is True
    assert checkpoint.previous_result == {"device": "gway-004"}
    assert checkpoint.context_provenance["device"].tokens == ("demo", "produce")
    assert checkpoint.previous_result_provenance is not None
    assert checkpoint.flags.interactive is True
    assert checkpoint.flags.explain is True
    assert checkpoint.flags.output_mode == "json"
    assert any(step.kind == "reload.exec" for step in trace)


def test_reload_outside_recipe_is_rejected(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with pytest.raises(ReloadError, match="only supported while a recipe statement is active"):
        runtime.execute(["reload"])


def test_reload_rejects_nested_recipe_continuation(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    child = tmp_path / "child.rx"
    parent = tmp_path / "parent.rx"
    child.write_text("reload\n", encoding="utf-8")
    parent.write_text(f"recipe {child}\n", encoding="utf-8")

    with pytest.raises(Exception, match="nested recipe resume is reserved for Chunk 7"):
        runtime.execute(["recipe", str(parent)])


def test_internal_resume_consumes_checkpoint_after_success(tmp_path: Path, monkeypatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    recipe = tmp_path / "resume-success.rx"
    recipe.write_text("demo produce\ndemo consume\n", encoding="utf-8")
    checkpoint_path = write_checkpoint_atomic(
        _resume_checkpoint(recipe),
        dispatcher.registry.paths.data_dir,
    )

    monkeypatch.setattr("gway.runtime.GwayRuntime", lambda: runtime)

    assert bootstrap._run_internal_resume(["--resume", str(checkpoint_path)]) == 0
    assert not checkpoint_path.exists()


def test_internal_resume_preserves_checkpoint_after_failure(tmp_path: Path, monkeypatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    recipe = tmp_path / "resume-failure.rx"
    recipe.write_text("demo produce\ndemo consume\n", encoding="utf-8")
    checkpoint_path = write_checkpoint_atomic(
        _resume_checkpoint(recipe),
        dispatcher.registry.paths.data_dir,
    )
    recipe.write_text("demo produce\ndemo produce\n", encoding="utf-8")

    monkeypatch.setattr("gway.runtime.GwayRuntime", lambda: runtime)

    result = bootstrap._run_internal_resume(["--resume", str(checkpoint_path)])
    assert result is not None and result != 0
    assert checkpoint_path.exists()


def test_atomic_checkpoint_round_trip_leaves_no_temporary_file(tmp_path: Path) -> None:
    recipe = tmp_path / "atomic.rx"
    recipe.write_text("reload\ndemo consume\n", encoding="utf-8")
    checkpoint = _resume_checkpoint(recipe)

    path = write_checkpoint_atomic(checkpoint, tmp_path / "data")

    assert read_checkpoint(path) == checkpoint
    assert not list(path.parent.glob("*.tmp"))
