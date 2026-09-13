from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.provenance import ExecutionFrameStack
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "provenance-project"
    root.mkdir()
    (root / "provenance_commands.py").write_text(
        """def status() -> dict[str, str]:
    return {"status": "ok"}


def produce() -> dict[str, str]:
    return {"device": "gway-004"}


def consume(*, device: str) -> str:
    return device
""",
        encoding="utf-8",
    )
    sys.modules.pop("provenance_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "provenance_commands"},
        )
    )
    return Dispatcher(registry)


def test_execution_frame_stack_tracks_parent_identity() -> None:
    frames = ExecutionFrameStack()

    with frames.scope("statement", tokens=["demo", "status"]) as statement:
        assert statement.id == "frame-1"
        assert statement.parent_id is None
        assert frames.current is statement
        with frames.scope("operation", operation="demo") as operation:
            assert operation.id == "frame-2"
            assert operation.parent_id == statement.id
            assert frames.frames == (statement, operation)
        assert frames.current is statement
        assert frames.last_completed is operation

    assert frames.current is None
    assert frames.frames == ()
    assert frames.last_completed is statement


def test_runtime_explain_links_statement_and_operation_frames(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with explain_scope() as trace:
        assert runtime.execute(["demo", "status"]) == {"status": "ok"}

    enters = [step for step in trace if step.kind == "runtime.frame.enter"]
    statement = next(step for step in enters if step.data["frame_kind"] == "statement")
    operation = next(step for step in enters if step.data["frame_kind"] == "operation")

    assert statement.data["parent_frame_id"] is None
    assert operation.data["parent_frame_id"] == statement.data["frame_id"]
    assert runtime.current_frame is None


def test_recipe_statement_frame_carries_source_location(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))
    recipe = tmp_path / "location.rx"
    recipe.write_text("# ignored\n\ndemo status\n", encoding="utf-8")

    with explain_scope() as trace:
        assert runtime.execute(["recipe", str(recipe)]) == {"status": "ok"}

    enters = [step for step in trace if step.kind == "runtime.frame.enter"]
    recipe_frame = next(step for step in enters if step.data["frame_kind"] == "recipe")
    statement = next(
        step
        for step in enters
        if step.data["frame_kind"] == "statement" and step.data.get("recipe_line") == 3
    )

    assert statement.data["recipe_path"] == str(recipe)
    assert statement.data["parent_frame_id"] == recipe_frame.data["frame_id"]
    assert runtime.current_frame is None


def test_recipe_context_resolution_reports_value_producer(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))
    recipe = tmp_path / "producer.rx"
    recipe.write_text("demo produce\ndemo consume\n", encoding="utf-8")

    with explain_scope() as trace:
        assert runtime.execute(["recipe", str(recipe)]) == "gway-004"

    context_step = next(
        step
        for step in trace
        if step.kind == "arguments.context"
        and step.data["command"] == ["consume"]
    )
    producer = context_step.data["provenance"]["device"]

    assert context_step.data["values"] == {"device": "gway-004"}
    assert producer["frame_kind"] == "operation"
    assert producer["tokens"] == ["demo", "produce"]
    assert producer["recipe_path"] == str(recipe)
    assert producer["recipe_line"] == 1


def test_provenance_metadata_does_not_become_recipe_context_key(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))
    recipe = tmp_path / "metadata.rx"
    recipe.write_text("demo produce\ndemo consume\n", encoding="utf-8")

    with explain_scope() as trace:
        assert runtime.execute(["recipe", str(recipe)]) == "gway-004"

    context_step = next(
        step
        for step in trace
        if step.kind == "arguments.context"
        and step.data["command"] == ["consume"]
    )
    publication = next(
        step
        for step in trace
        if step.kind == "chain.stage.result"
        and step.data["result"] == {"device": "gway-004"}
    )

    assert context_step.data["values"] == {"device": "gway-004"}
    assert "provenance" not in context_step.data["values"]
    assert publication.data["provenance"]["tokens"] == ["demo", "produce"]
