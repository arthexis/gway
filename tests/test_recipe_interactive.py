from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.recipe import run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "recipe-interactive-project"
    root.mkdir()
    (root / "recipe_interactive_commands.py").write_text(
        '''def named() -> dict[str, str]:
    return {"token": "context-token"}


def use_named(*, token: str) -> str:
    return token
''',
        encoding="utf-8",
    )
    sys.modules.pop("recipe_interactive_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "recipe_interactive_commands"},
        )
    )
    return Dispatcher(registry)


def test_interactive_recipe_prompts_for_missing_required_value(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe = tmp_path / "prompt.rx"
    recipe.write_text("demo use-named\n", encoding="utf-8")
    answers = iter(["prompt-token"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    assert run_recipe(recipe, _dispatcher(tmp_path), interactive=True) == "prompt-token"


def test_recipe_context_is_used_before_interactive_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe = tmp_path / "context.rx"
    recipe.write_text("demo named\ndemo use-named\n", encoding="utf-8")

    def fail_input() -> str:
        raise AssertionError("interactive prompt should not run when context satisfies token")

    monkeypatch.setattr("builtins.input", fail_input)

    assert run_recipe(recipe, _dispatcher(tmp_path), interactive=True) == "context-token"
