from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.recipe import RecipeError, recipe_statements, run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "recipe-project"
    root.mkdir()
    (root / "recipe_commands.py").write_text(
        """CALLS = []


def named() -> dict[str, str]:
    CALLS.append(\"named\")
    return {\"customer\": \"cust-1\", \"charger\": \"chg-1\"}


def scalar() -> str:
    CALLS.append(\"operation\")
    return \"alpha\"


def use_named(*, customer: str, charger: str) -> str:
    return f\"{customer}:{charger}\"


def echo(value: str) -> str:
    return value


def fitness_true(value: str) -> bool:
    CALLS.append(f\"fitness_true:{value}\")
    return value == \"alpha\"


def fitness_false(value: str) -> bool:
    CALLS.append(f\"fitness_false:{value}\")
    return False


def fitness_debug(value: str) -> dict[str, str]:
    CALLS.append(f\"fitness_debug:{value}\")
    return {\"reason\": \"not ready\"}


def fitness_named(*, customer: str, charger: str) -> bool:
    CALLS.append(f\"fitness_named:{customer}:{charger}\")
    return customer == \"cust-1\" and charger == \"chg-1\"


def fitness_no_input() -> bool:
    CALLS.append(\"fitness_no_input\")
    return True


def calls() -> list[str]:
    return list(CALLS)
""",
        encoding="utf-8",
    )
    sys.modules.pop("recipe_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "recipe_commands"},
        )
    )
    return Dispatcher(registry)


def test_recipe_statements_skip_blank_and_full_line_comments(tmp_path: Path) -> None:
    path = tmp_path / "sample.rx"
    path.write_text(
        "\n# comment\n  # indented comment\nstore --message 'hello world'\n",
        encoding="utf-8",
    )

    statements = list(recipe_statements(path))

    assert len(statements) == 1
    assert statements[0].line == 4
    assert statements[0].tokens == ("store", "--message", "hello world")


def test_recipe_fitness_parses_operation_and_predicate(tmp_path: Path) -> None:
    path = tmp_path / "fitness.rx"
    path.write_text("upgrade arthexis --> arthexis good\n", encoding="utf-8")

    statements = list(recipe_statements(path))

    assert len(statements) == 1
    assert statements[0].tokens == ("upgrade", "arthexis")
    assert statements[0].fitness_tokens == ("arthexis", "good")
    assert statements[0].line == 1
    assert statements[0].end_line == 1


def test_recipe_fitness_continuation_flags_attach_to_operation(tmp_path: Path) -> None:
    path = tmp_path / "fitness.rx"
    path.write_text(
        "upgrade arthexis --> arthexis good:\n"
        "    --install\n"
        "    --service\n"
        "    --role Watchtower\n",
        encoding="utf-8",
    )

    statements = list(recipe_statements(path))

    assert len(statements) == 1
    assert statements[0].tokens == (
        "upgrade",
        "arthexis",
        "--install",
        "--service",
        "--role",
        "Watchtower",
    )
    assert statements[0].fitness_tokens == ("arthexis", "good")
    assert statements[0].line == 1
    assert statements[0].end_line == 4


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("--> arthexis good\n", "requires an operation"),
        ("upgrade arthexis -->\n", "requires a fitness function"),
        ("upgrade arthexis --> arthexis good --> other good\n", "exactly one '-->'"),
        ("upgrade arthexis --> arthexis good --details\n", "do not accept inline flags"),
    ],
)
def test_recipe_fitness_rejects_malformed_syntax(
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    path = tmp_path / "broken.rx"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(RecipeError, match=message.replace("-->", r"\-\->")):
        list(recipe_statements(path))


def test_recipe_fitness_true_returns_original_operation_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "fitness.rx"
    path.write_text("demo scalar --> demo fitness-true\n", encoding="utf-8")

    assert run_recipe(path, dispatcher) == "alpha"
    assert dispatcher.invoke("demo", ("calls",)) == ["operation", "fitness_true:alpha"]


def test_recipe_fitness_false_fails_semantically(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "fitness.rx"
    path.write_text("demo scalar --> demo fitness-false\n", encoding="utf-8")

    with pytest.raises(RecipeError, match="fitness predicate returned false"):
        run_recipe(path, dispatcher)
    assert dispatcher.invoke("demo", ("calls",)) == ["operation", "fitness_false:alpha"]


def test_recipe_fitness_non_boolean_is_failed_diagnostic_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "fitness.rx"
    path.write_text("demo scalar --> demo fitness-debug\n", encoding="utf-8")

    with pytest.raises(
        RecipeError,
        match=r"fitness predicate returned non-boolean diagnostic value .*not ready",
    ):
        run_recipe(path, dispatcher)
    assert dispatcher.invoke("demo", ("calls",)) == ["operation", "fitness_debug:alpha"]


def test_recipe_fitness_consumes_mapping_result_from_semantic_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "fitness.rx"
    path.write_text("demo named --> demo fitness-named\n", encoding="utf-8")

    assert run_recipe(path, dispatcher) == {"customer": "cust-1", "charger": "chg-1"}
    assert dispatcher.invoke("demo", ("calls",)) == [
        "named",
        "fitness_named:cust-1:chg-1",
    ]


def test_recipe_fitness_may_ignore_operation_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "fitness.rx"
    path.write_text("demo scalar --> demo fitness-no-input\n", encoding="utf-8")

    assert run_recipe(path, dispatcher) == "alpha"
    assert dispatcher.invoke("demo", ("calls",)) == ["operation", "fitness_no_input"]


def test_recipe_continuation_normalizes_to_one_logical_statement(tmp_path: Path) -> None:
    path = tmp_path / "continued.rx"
    path.write_text(
        "store:\n"
        "    --customer cust-9\n"
        "    --charger chg-9\n"
        "demo use-named\n",
        encoding="utf-8",
    )

    statements = list(recipe_statements(path))

    assert len(statements) == 2
    assert statements[0].line == 1
    assert statements[0].end_line == 3
    assert statements[0].tokens == (
        "store",
        "--customer",
        "cust-9",
        "--charger",
        "chg-9",
    )
    assert statements[1].line == 4


def test_recipe_continuation_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    path = tmp_path / "continued.rx"
    path.write_text(
        "store:\n"
        "    --customer cust-9\n"
        "\n"
        "    # explanation\n"
        "    --charger chg-9\n",
        encoding="utf-8",
    )

    statements = list(recipe_statements(path))

    assert len(statements) == 1
    assert statements[0].end_line == 5
    assert statements[0].tokens[-2:] == ("--charger", "chg-9")


def test_recipe_continuation_requires_indented_arguments(tmp_path: Path) -> None:
    path = tmp_path / "broken.rx"
    path.write_text("store:\ndemo scalar\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"broken\.rx:1: continuation requires indented"):
        list(recipe_statements(path))


def test_recipe_continuation_rejects_nested_indentation(tmp_path: Path) -> None:
    path = tmp_path / "broken.rx"
    path.write_text(
        "store:\n"
        "    --customer cust-9\n"
        "        --charger chg-9\n",
        encoding="utf-8",
    )

    with pytest.raises(RecipeError, match=r"broken\.rx:3: nested or inconsistent"):
        list(recipe_statements(path))


def test_recipe_continuation_rejects_second_operation(tmp_path: Path) -> None:
    path = tmp_path / "broken.rx"
    path.write_text("store:\n    demo scalar\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"broken\.rx:2: continuation lines must contain"):
        list(recipe_statements(path))


def test_recipe_requires_rx_extension(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("store --name demo\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"sample\.txt: recipe files must use the \.rx extension"):
        list(recipe_statements(path))


def test_recipe_reports_malformed_quoting_with_line_number(tmp_path: Path) -> None:
    path = tmp_path / "broken.rx"
    path.write_text("# ok\nstore --name 'unterminated\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"broken\.rx:2:"):
        list(recipe_statements(path))


def test_run_recipe_shares_context_and_returns_final_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "shared.rx"
    path.write_text(
        "store --customer cust-9 --charger chg-9\ndemo use-named\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "cust-9:chg-9"


def test_run_recipe_executes_continuation_like_one_line_form(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "continued.rx"
    path.write_text(
        "store:\n"
        "    --customer cust-9\n"
        "    --charger chg-9\n"
        "demo use-named\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "cust-9:chg-9"


def test_run_recipe_newline_does_not_transfer_scalar_positionally(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "newline.rx"
    path.write_text("demo scalar\ndemo echo\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"newline\.rx:2:"):
        run_recipe(path, dispatcher)


def test_run_recipe_preserves_explicit_chain_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "chain.rx"
    path.write_text("demo scalar - demo echo\n", encoding="utf-8")

    assert run_recipe(path, dispatcher) == "alpha"


def test_run_recipe_wraps_statement_failure_with_source_location(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "failure.rx"
    path.write_text("store --name ok\nmissing command\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"failure\.rx:2:"):
        run_recipe(path, dispatcher)
