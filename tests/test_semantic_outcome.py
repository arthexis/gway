from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.chain import run_statement
from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.outcome import CommandOutcome, SemanticFailure, failure, success
from gway.project import Project
from gway.recipe import RecipeError
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _runtime(tmp_path: Path) -> GwayRuntime:
    root = tmp_path / "semantic-project"
    root.mkdir()
    (root / "semantic_commands.py").write_text(
        """from gway import failure, success


def semantic_fail():
    return failure({"success": False, "reason": "blocked"}, message="blocked by semantic check")


def semantic_fail_input(value):
    return failure({"success": False, "reason": "blocked", "input": value}, message="blocked by semantic check")


def semantic_ok():
    return success("seed")


def passthrough(value):
    return value + ":next"


def plain_mapping():
    return {"success": False, "meaning": "ordinary data"}


def explode():
    raise RuntimeError("downstream stage executed")
""",
        encoding="utf-8",
    )
    sys.modules.pop("semantic_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "semantic_commands"},
        )
    )
    return GwayRuntime(Dispatcher(registry))


def test_explicit_success_outcome_unwraps_before_chain_transfer(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    result = runtime.execute(["demo", "semantic_ok", "-", "demo", "passthrough"])

    assert result == "seed:next"


def test_explicit_failure_outcome_stops_remaining_chain_stages(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    with pytest.raises(SemanticFailure, match="blocked by semantic check") as exc_info:
        runtime.execute(["demo", "semantic_fail", "-", "demo", "explode"])

    assert exc_info.value.outcome.value == {"success": False, "reason": "blocked"}


def test_plain_success_mapping_remains_ordinary_data(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    assert runtime.execute(["demo", "plain_mapping"]) == {
        "success": False,
        "meaning": "ordinary data",
    }


def test_direct_cli_unwraps_success_outcome(tmp_path: Path, capsys) -> None:
    runtime = _runtime(tmp_path)

    assert main(["demo", "semantic_ok"], dispatcher=runtime.dispatcher) == 0
    assert capsys.readouterr().out.strip() == "seed"


def test_direct_cli_reports_semantic_failure_without_traceback(tmp_path: Path, capsys) -> None:
    runtime = _runtime(tmp_path)

    assert main(["demo", "semantic_fail"], dispatcher=runtime.dispatcher) == 2
    captured = capsys.readouterr()
    assert "blocked by semantic check" in captured.err
    assert "Traceback" not in captured.err


def test_recipe_fails_fast_on_semantic_failure(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    recipe = tmp_path / "semantic-failure.rx"
    recipe.write_text("demo semantic_fail\ndemo explode\n", encoding="utf-8")

    with pytest.raises(RecipeError, match="blocked by semantic check") as exc_info:
        runtime.execute(["recipe", str(recipe)])

    assert exc_info.value.line == 1


def test_semantic_failure_is_explained_without_publishing_stage_result(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    with explain_scope() as trace, pytest.raises(SemanticFailure):
        runtime.execute(["demo", "semantic_fail"])

    outcome = next(step for step in trace if step.kind == "runtime.operation.outcome")
    assert outcome.data["success"] is False
    assert outcome.data["result"] == {"success": False, "reason": "blocked"}
    assert outcome.data["outcome_message"] == "blocked by semantic check"
    assert outcome.data["provenance"]["operation"] == "demo"
    assert any(step.kind == "command.outcome" for step in trace)
    assert any(step.kind == "chain.stage.failure" for step in trace)
    assert not [step for step in trace if step.kind == "chain.stage.result"]
    assert not [step for step in trace if step.kind == "chain.result"]


def test_resumed_chain_boundary_uses_same_semantic_failure_contract(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    tokens = (
        "demo",
        "semantic_ok",
        "-",
        "demo",
        "semantic_fail_input",
        "-",
        "demo",
        "explode",
    )

    with runtime.frame_scope("statement", tokens=tokens):
        with pytest.raises(SemanticFailure, match="blocked by semantic check") as exc_info:
            run_statement(
                runtime.dispatcher,
                tokens,
                runtime=runtime,
                start_stage_index=1,
                initial_result="seed",
                has_initial_result=True,
            )

    assert exc_info.value.outcome.value["input"] == "seed"


def test_outcome_contract_requires_boolean_success() -> None:
    with pytest.raises(TypeError, match="must be a boolean"):
        CommandOutcome(1)  # type: ignore[arg-type]


def test_public_helpers_build_explicit_outcomes() -> None:
    assert success("ok") == CommandOutcome(True, "ok")
    assert failure("bad", message="no") == CommandOutcome(False, "bad", "no")
