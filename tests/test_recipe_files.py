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
        """def named() -> dict[str, str]:
    return {\"customer\": \"cust-1\", \"charger\": \"chg-1\"}


def scalar() -> str:
    return \"alpha\"


def use_named(*, customer: str, charger: str) -> str:
    return f\"{customer}:{charger}\"


def echo(value: str) -> str:
    return value
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
