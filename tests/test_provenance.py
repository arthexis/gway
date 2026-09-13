from __future__ import annotations

import sys
from pathlib import Path

from gway.chain import run_statement
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.provenance import ContinuationPoint, ExecutionFrameStack
from gway.recipe import RecipeSession
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


def test_continuation_stack_restores_parent_recipe_pointer() -> None:
    frames = ExecutionFrameStack()
    parent = ContinuationPoint("parent.rx", 1, 4, 2, 8)
    child = ContinuationPoint("child.rx", 1, 2, None, None)

    with frames.continuation_scope(parent):
        assert frames.current_continuation is parent
        assert frames.continuations == (parent,)
        with frames.continuation_scope(child):
            assert frames.current_continuation is child
            assert frames.continuations == (parent, child)
        assert frames.current_continuation is parent
        assert frames.continuations == (parent,)

    assert frames.current_continuation is None
    assert frames.continuations == ()


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


def test_standalone_statement_solve_has_statement_provenance(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    with explain_scope() as trace:
        assert run_statement(dispatcher, ["%", "hello"]) == "hello"

    enters = [step for step in trace if step.kind == "runtime.frame.enter"]
    statements = [step for step in enters if step.data["frame_kind"] == "statement"]
    publication = next(step for step in trace if step.kind == "chain.stage.result")

    assert len(statements) == 1
    assert publication.data["provenance"]["frame_kind"] == "statement"
    assert publication.data["provenance"]["frame_id"] == statements[0].data["frame_id"]


def test_recipe_session_keeps_caller_mapping_live(tmp_path: Path) -> None:
    shared = {"device": "before"}
    session = RecipeSession(_dispatcher(tmp_path), context=shared)

    shared["device"] = "after"
    assert session.run(["demo", "consume"]) == "after"
    assert session.run(["demo", "produce"]) == {"device": "gway-004"}

    assert shared["device"] == "gway-004"
    assert shared["result"] == {"device": "gway-004"}


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


def test_recipe_trace_records_current_and_next_statement_pointer(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))
    recipe = tmp_path / "pointer.rx"
    recipe.write_text("# header\n\ndemo status\n\ndemo status\n", encoding="utf-8")

    with explain_scope() as trace:
        assert runtime.execute(["recipe", str(recipe)]) == {"status": "ok"}

    starts = [step for step in trace if step.kind == "recipe.statement.start"]
    assert starts[0].data["continuation"] == {
        "recipe_path": str(recipe),
        "statement_index": 1,
        "line": 3,
        "next_statement_index": 2,
        "next_line": 5,
    }
    assert starts[1].data["continuation"] == {
        "recipe_path": str(recipe),
        "statement_index": 2,
        "line": 5,
        "next_statement_index": None,
        "next_line": None,
    }


def test_nested_recipe_trace_carries_continuation_stack(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))
    child = tmp_path / "child.rx"
    parent = tmp_path / "parent.rx"
    child.write_text("demo status\n", encoding="utf-8")
    parent.write_text(f"recipe {child}\ndemo status\n", encoding="utf-8")

    with explain_scope() as trace:
        assert runtime.execute(["recipe", str(parent)]) == {"status": "ok"}

    starts = [step for step in trace if step.kind == "recipe.statement.start"]
    parent_first, child_only, parent_second = starts

    assert [item["recipe_path"] for item in parent_first.data["continuation_stack"]] == [
        str(parent)
    ]
    assert [item["recipe_path"] for item in child_only.data["continuation_stack"]] == [
        str(parent),
        str(child),
    ]
    assert [item["recipe_path"] for item in parent_second.data["continuation_stack"]] == [
        str(parent)
    ]
    assert runtime.frames.current_continuation is None
    assert runtime.frames.continuations == ()


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
