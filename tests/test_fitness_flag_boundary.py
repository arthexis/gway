from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.recipe import RecipeError, run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "fitness-flags"
    root.mkdir()
    (root / "fitness_flags.py").write_text(
        '''CALLS = []


def operate(*, role: str = "operation-default", service: bool = False) -> str:
    CALLS.append(("operate", role, service))
    return "ready"


def good(*, role: str = "fitness-default", service: bool = False) -> bool:
    CALLS.append(("good", role, service))
    return role == "fitness-default" and service is False


def bad() -> bool:
    CALLS.append(("bad",))
    return False


def debug():
    CALLS.append(("debug",))
    return {"reason": "not ready", "state": "warming"}


def calls():
    return list(CALLS)
''',
        encoding="utf-8",
    )
    sys.modules.pop("fitness_flags", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "fitness_flags"},
        )
    )
    return Dispatcher(registry)


def test_continuation_flags_belong_only_to_operation(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "flags.rx"
    path.write_text(
        "demo operate --> demo good:\n"
        "    --role Watchtower\n"
        "    --service\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "ready"
    assert dispatcher.invoke("demo", ("calls",)) == [
        ("operate", "Watchtower", True),
        ("good", "fitness-default", False),
    ]


def test_fitness_command_standalone_keeps_its_own_flags(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run(
        "demo",
        ["good", "--role", "manual", "--service"],
    ) is False
    assert dispatcher.invoke("demo", ("calls",)) == [
        ("good", "manual", True),
    ]


def test_explain_distinguishes_operation_fitness_and_final_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "explain.rx"
    path.write_text("demo operate --> demo good\n", encoding="utf-8")

    with explain_scope() as trace:
        result = run_recipe(path, dispatcher)

    assert result == "ready"
    chain_starts = [step for step in trace if step.kind == "chain.start"]
    assert any(step.data["tokens"] == ["demo", "operate"] for step in chain_starts)
    assert any(step.data["tokens"] == ["demo", "good"] for step in chain_starts)

    fitness = next(step for step in trace if step.kind == "recipe.fitness.result")
    assert fitness.data["fitness_tokens"] == ["demo", "good"]
    assert fitness.data["satisfied"] is True
    assert fitness.data["boolean"] is True
    assert fitness.data["result"] is True

    statement = next(step for step in trace if step.kind == "recipe.statement.result")
    assert statement.data["result"] == "ready"


def test_false_fitness_is_explained_as_unsatisfied_boolean(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "false.rx"
    path.write_text("demo operate --> demo bad\n", encoding="utf-8")

    with explain_scope() as trace:
        with pytest.raises(RecipeError, match="fitness predicate returned false"):
            run_recipe(path, dispatcher)

    fitness = next(step for step in trace if step.kind == "recipe.fitness.result")
    assert fitness.data["satisfied"] is False
    assert fitness.data["boolean"] is True
    assert fitness.data["result"] is False


def test_non_boolean_fitness_preserves_diagnostic_value_in_explain(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "debug.rx"
    path.write_text("demo operate --> demo debug\n", encoding="utf-8")

    with explain_scope() as trace:
        with pytest.raises(RecipeError, match="non-boolean diagnostic value"):
            run_recipe(path, dispatcher)

    fitness = next(step for step in trace if step.kind == "recipe.fitness.result")
    assert fitness.data["satisfied"] is False
    assert fitness.data["boolean"] is False
    assert fitness.data["result"] == {"reason": "not ready", "state": "warming"}
