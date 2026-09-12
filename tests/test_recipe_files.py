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
    root = tmp_path / "recipe-file-project"
    root.mkdir()
    (root / "recipe_file_commands.py").write_text(
        '''def publish() -> dict[str, str]:
    return {"token": "from-context"}


def consume(*, token: str) -> str:
    return token


def scalar() -> str:
    return "from-scalar"


def echo(value: str) -> str:
    return value


def phrase(value: str) -> str:
    return value
''',
        encoding="utf-8",
    )
    sys.modules.pop("recipe_file_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "recipe_file_commands"},
        )
    )
    return Dispatcher(registry)


def test_recipe_file_uses_shared_named_context_and_dash_transfer(tmp_path: Path) -> None:
    recipe = tmp_path / "sample.rx"
    recipe.write_text(
        """# comments and blanks are ignored

demo publish
demo consume
demo scalar - demo echo
""",
        encoding="utf-8",
    )
    results: list[object] = []

    result = run_recipe(recipe, _dispatcher(tmp_path), on_result=results.append)

    assert results == [
        {"token": "from-context"},
        "from-context",
        "from-scalar",
    ]
    assert result == "from-scalar"


def test_recipe_tokenizer_preserves_quoted_argument(tmp_path: Path) -> None:
    recipe = tmp_path / "quoted.rx"
    recipe.write_text('demo phrase "two words"\n', encoding="utf-8")

    statements = list(recipe_statements(recipe))

    assert len(statements) == 1
    assert statements[0].line == 1
    assert statements[0].tokens == ("demo", "phrase", "two words")


def test_recipe_rejects_non_rx_extension(tmp_path: Path) -> None:
    recipe = tmp_path / "sample.txt"
    recipe.write_text("demo scalar\n", encoding="utf-8")

    with pytest.raises(RecipeError, match=r"\.rx extension"):
        list(recipe_statements(recipe))


def test_recipe_reports_statement_line_and_stops(tmp_path: Path) -> None:
    recipe = tmp_path / "failure.rx"
    recipe.write_text(
        """# line one

demo publish
demo missing-command
demo consume
""",
        encoding="utf-8",
    )
    results: list[object] = []

    with pytest.raises(RecipeError, match=r"failure\.rx:4:"):
        run_recipe(recipe, _dispatcher(tmp_path), on_result=results.append)

    assert results == [{"token": "from-context"}]


def test_recipe_reports_tokenization_line(tmp_path: Path) -> None:
    recipe = tmp_path / "broken.rx"
    recipe.write_text('demo phrase "unterminated\n', encoding="utf-8")

    with pytest.raises(RecipeError, match=r"broken\.rx:1:"):
        list(recipe_statements(recipe))
