from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.checkpoint import CheckpointFlags, ResumeCheckpoint, recipe_identity
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.provenance import ContinuationPoint, ValueProvenance
from gway.registry import Registry
from gway.resume import ResumeError, resume_recipe
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "resume-project"
    root.mkdir()
    (root / "resume_commands.py").write_text(
        """def skipped() -> None:
    raise RuntimeError("skipped statement executed")


def current() -> None:
    raise RuntimeError("checkpointed statement executed again")


def consume(*, device: str) -> str:
    return device


def zero() -> str:
    return "ok"


def ask(*, token: str) -> str:
    return token
""",
        encoding="utf-8",
    )
    sys.modules.pop("resume_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "resume_commands"},
        )
    )
    return Dispatcher(registry)


def _checkpoint(
    recipe: Path,
    *,
    current_index: int = 2,
    current_line: int = 2,
    next_index: int | None = 3,
    next_line: int | None = 3,
    context: dict[str, object] | None = None,
    provenance: dict[str, ValueProvenance] | None = None,
    previous_result: object = "previous",
    has_previous_result: bool = True,
    flags: CheckpointFlags | None = None,
) -> ResumeCheckpoint:
    return ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(
            str(recipe),
            current_index,
            current_line,
            next_index,
            next_line,
        ),
        context=context or {},  # type: ignore[arg-type]
        context_provenance=provenance or {},
        has_previous_result=has_previous_result,
        previous_result=previous_result if has_previous_result else None,  # type: ignore[arg-type]
        flags=flags or CheckpointFlags(),
    )


def test_resume_starts_at_next_statement_and_restores_context_provenance(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    recipe = tmp_path / "resume.rx"
    recipe.write_text("demo skipped\ndemo current\ndemo consume\n", encoding="utf-8")
    producer = ValueProvenance(
        frame_id="frame-before-reload",
        frame_kind="operation",
        operation="demo",
        tokens=("demo", "produce"),
        recipe_path=str(recipe),
        recipe_line=2,
    )
    checkpoint = _checkpoint(
        recipe,
        context={"device": "gway-004", "result": "previous"},
        provenance={"device": producer},
    )

    with explain_scope() as trace:
        assert resume_recipe(checkpoint, dispatcher, runtime=runtime) == "gway-004"

    statements = [step for step in trace if step.kind == "recipe.statement.start"]
    assert [step.data["line"] for step in statements] == [3]
    context_step = next(
        step
        for step in trace
        if step.kind == "arguments.context" and step.data["command"] == ["consume"]
    )
    assert context_step.data["values"] == {"device": "gway-004"}
    assert context_step.data["provenance"]["device"]["frame_id"] == "frame-before-reload"
    assert runtime.frames.continuations == ()
    assert runtime.current_frame is None


def test_resume_does_not_parse_skipped_statements(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "lazy.rx"
    recipe.write_text('demo "unterminated\ndemo current\ndemo zero\n', encoding="utf-8")
    checkpoint = _checkpoint(recipe)

    assert resume_recipe(checkpoint, dispatcher) == "ok"


def test_resume_does_not_chain_previous_result_positionally_across_newline(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "no-transfer.rx"
    recipe.write_text("demo skipped\ndemo current\ndemo zero\n", encoding="utf-8")
    checkpoint = _checkpoint(recipe, previous_result=["would", "break", "zero"])

    assert resume_recipe(checkpoint, dispatcher) == "ok"


def test_resume_restores_interactive_prompt_flag(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "interactive.rx"
    recipe.write_text("demo skipped\ndemo current\ndemo ask\n", encoding="utf-8")
    checkpoint = _checkpoint(
        recipe,
        flags=CheckpointFlags(interactive=True, explain=True, output_mode="json"),
    )

    with explain_scope() as trace:
        result = resume_recipe(checkpoint, dispatcher, prompt=lambda name: f"answer:{name}")

    assert result == "answer:token"
    resume_start = next(step for step in trace if step.kind == "resume.start")
    assert resume_start.data["interactive"] is True
    assert resume_start.data["explain"] is True
    assert resume_start.data["output_mode"] == "json"


def test_resume_completed_recipe_returns_previous_result_without_execution(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "done.rx"
    recipe.write_text("demo skipped\ndemo current\n", encoding="utf-8")
    checkpoint = _checkpoint(
        recipe,
        current_index=2,
        current_line=2,
        next_index=None,
        next_line=None,
        previous_result=None,
    )

    with explain_scope() as trace:
        assert resume_recipe(checkpoint, dispatcher) is None

    assert not [step for step in trace if step.kind == "recipe.statement.start"]
    assert any(step.kind == "resume.result" for step in trace)


def test_resume_rejects_changed_recipe_source(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "changed.rx"
    recipe.write_text("demo skipped\ndemo current\ndemo zero\n", encoding="utf-8")
    checkpoint = _checkpoint(recipe)
    recipe.write_text("demo skipped\ndemo current\ndemo consume\n", encoding="utf-8")

    with pytest.raises(ResumeError, match="recipe changed"):
        resume_recipe(checkpoint, dispatcher)


def test_resume_rejects_non_adjacent_next_statement(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "jump.rx"
    recipe.write_text(
        "demo skipped\ndemo current\ndemo zero\ndemo zero\n",
        encoding="utf-8",
    )
    checkpoint = _checkpoint(recipe, next_index=4, next_line=4)

    with pytest.raises(ResumeError, match="immediately follow"):
        resume_recipe(checkpoint, dispatcher)
