from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.recipe import RecipeSession
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "recipe-project"
    root.mkdir()
    (root / "recipe_commands.py").write_text(
        '''def named() -> dict[str, str]:
    return {"token": "context-token"}


def scalar() -> str:
    return "scalar-token"


def use_named(*, token: str) -> str:
    return token


def use_optional(*, token: str = "default-token") -> str:
    return token


def echo(value: str) -> str:
    return value
''',
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


def test_new_statement_uses_named_context_without_positional_transfer(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    assert session.run(["demo", "named"]) == {"token": "context-token"}
    assert session.run(["demo", "use-named"]) == "context-token"


def test_new_statement_does_not_feed_scalar_result_positionally(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    assert session.run(["demo", "scalar"]) == "scalar-token"
    with pytest.raises(SystemExit):
        session.run(["demo", "echo"])


def test_explicit_dash_still_feeds_previous_result_positionally(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    assert session.run(["demo", "scalar", "-", "demo", "echo"]) == "scalar-token"


def test_explicit_named_argument_wins_over_recipe_context(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    session.run(["demo", "named"])
    assert session.run(["demo", "use-named", "--token", "explicit-token"]) == "explicit-token"


def test_context_precedes_function_default_for_named_options(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    session.run(["demo", "named"])
    assert session.run(["demo", "use-optional"]) == "context-token"
