from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.recipe import RecipeError, recipe_statements, run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "fitness-acceptance"
    root.mkdir()
    (root / "fitness_acceptance.py").write_text(
        '''CALLS = []


def scalar() -> str:
    CALLS.append("scalar")
    return "alpha"


def scalar_good(value: str) -> bool:
    CALLS.append(f"scalar_good:{value}")
    return value == "alpha"


def zero_good() -> bool:
    CALLS.append("zero_good")
    return True


def mapping() -> dict[str, str]:
    CALLS.append("mapping")
    return {"customer": "cust-1", "charger": "chg-1"}


def mapping_good(*, customer: str, charger: str) -> bool:
    CALLS.append(f"mapping_good:{customer}:{charger}")
    return customer == "cust-1" and charger == "chg-1"


def false_good(value: str) -> bool:
    CALLS.append(f"false_good:{value}")
    return False


def diagnostic(value: str) -> dict[str, str]:
    CALLS.append(f"diagnostic:{value}")
    return {"reason": "not ready", "value": value}


def operate(*, role: str = "operation-default", service: bool = False) -> str:
    CALLS.append(f"operate:{role}:{service}")
    return "ready"


def flags_good(*, role: str = "fitness-default", service: bool = False) -> bool:
    CALLS.append(f"flags_good:{role}:{service}")
    return role == "fitness-default" and service is False


def echo(value: str) -> str:
    CALLS.append(f"echo:{value}")
    return value


def calls() -> list[str]:
    return list(CALLS)
''',
        encoding="utf-8",
    )
    sys.modules.pop("fitness_acceptance", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "fitness_acceptance"},
        )
    )
    return Dispatcher(registry)


def test_concrete_upgrade_arthexis_shape_is_one_logical_statement(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.rx"
    path.write_text("upgrade arthexis --> arthexis good\n", encoding="utf-8")

    statements = list(recipe_statements(path))

    assert len(statements) == 1
    assert statements[0].tokens == ("upgrade", "arthexis")
    assert statements[0].fitness_tokens == ("arthexis", "good")
    assert statements[0].line == statements[0].end_line == 1


def test_single_evaluation_contract_and_result_preservation(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "scalar.rx"
    path.write_text("demo scalar --> demo scalar-good\n", encoding="utf-8")

    with explain_scope() as trace:
        result = run_recipe(path, dispatcher)

    assert result == "alpha"
    assert dispatcher.invoke("demo", ("calls",)) == ["scalar", "scalar_good:alpha"]

    chain_starts = [step for step in trace if step.kind == "chain.start"]
    assert len(chain_starts) == 2
    fitness = next(step for step in trace if step.kind == "recipe.fitness.result")
    assert fitness.data["satisfied"] is True
    assert fitness.data["boolean"] is True
    statement = next(step for step in trace if step.kind == "recipe.statement.result")
    assert statement.data["result"] == "alpha"


def test_signature_aware_zero_arg_and_mapping_context_consumption(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    zero_path = tmp_path / "zero.rx"
    zero_path.write_text("demo scalar --> demo zero-good\n", encoding="utf-8")

    assert run_recipe(zero_path, dispatcher) == "alpha"
    assert dispatcher.invoke("demo", ("calls",)) == ["scalar", "zero_good"]

    dispatcher = _dispatcher(tmp_path / "second")
    mapping_path = tmp_path / "mapping.rx"
    mapping_path.write_text("demo mapping --> demo mapping-good\n", encoding="utf-8")

    expected = {"customer": "cust-1", "charger": "chg-1"}
    assert run_recipe(mapping_path, dispatcher) == expected
    assert dispatcher.invoke("demo", ("calls",)) == [
        "mapping",
        "mapping_good:cust-1:chg-1",
    ]


def test_false_and_non_boolean_fitness_fail_semantically_with_diagnostics(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    false_path = tmp_path / "false.rx"
    false_path.write_text("demo scalar --> demo false-good\n", encoding="utf-8")

    with explain_scope() as false_trace:
        with pytest.raises(RecipeError, match="fitness predicate returned false"):
            run_recipe(false_path, dispatcher)

    false_step = next(step for step in false_trace if step.kind == "recipe.fitness.result")
    assert false_step.data["satisfied"] is False
    assert false_step.data["boolean"] is True
    assert false_step.data["result"] is False

    dispatcher = _dispatcher(tmp_path / "second")
    diagnostic_path = tmp_path / "diagnostic.rx"
    diagnostic_path.write_text("demo scalar --> demo diagnostic\n", encoding="utf-8")

    with explain_scope() as diagnostic_trace:
        with pytest.raises(RecipeError, match="non-boolean diagnostic value"):
            run_recipe(diagnostic_path, dispatcher)

    diagnostic_step = next(
        step for step in diagnostic_trace if step.kind == "recipe.fitness.result"
    )
    assert diagnostic_step.data["satisfied"] is False
    assert diagnostic_step.data["boolean"] is False
    assert diagnostic_step.data["result"] == {"reason": "not ready", "value": "alpha"}


def test_continuation_flags_stay_left_and_ordinary_recipes_are_unchanged(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    flags_path = tmp_path / "flags.rx"
    flags_path.write_text(
        "demo operate --> demo flags-good:\n"
        "    --role Watchtower\n"
        "    --service\n",
        encoding="utf-8",
    )

    assert run_recipe(flags_path, dispatcher) == "ready"
    assert dispatcher.invoke("demo", ("calls",)) == [
        "operate:Watchtower:True",
        "flags_good:fitness-default:False",
    ]

    dispatcher = _dispatcher(tmp_path / "ordinary")
    ordinary_path = tmp_path / "ordinary.rx"
    ordinary_path.write_text("demo scalar - demo echo\n", encoding="utf-8")
    assert run_recipe(ordinary_path, dispatcher) == "alpha"

    continued_path = tmp_path / "continued.rx"
    continued_path.write_text(
        "demo operate:\n"
        "    --role Watchtower\n"
        "    --service\n",
        encoding="utf-8",
    )
    assert run_recipe(continued_path, dispatcher) == "ready"
