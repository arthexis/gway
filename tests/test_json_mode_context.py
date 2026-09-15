from __future__ import annotations

import os
import sys
from pathlib import Path

import gway.entrypoint as entrypoint
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "json-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "json-demo"

[adapter]
type = "python"
module = "commands"
""",
        encoding="utf-8",
    )
    (root / "commands.py").write_text(
        """def mode(*, json: bool = False) -> dict[str, bool]:
    return {"json": json}
""",
        encoding="utf-8",
    )
    sys.modules.pop("commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(Project.from_path(root))
    return Dispatcher(registry)


def test_entrypoint_seeds_global_json_mode_and_restores_environment(monkeypatch) -> None:
    observed: list[tuple[list[str], str | None]] = []

    def fake_bootstrap(arguments):
        observed.append((list(arguments), os.environ.get("_GWAY_JSON_MODE")))
        return 0

    monkeypatch.delenv("_GWAY_JSON_MODE", raising=False)
    monkeypatch.setattr("gway.bootstrap.main", fake_bootstrap)

    assert entrypoint.main(["--json", "list"]) == 0
    assert observed == [(["--json", "list"], "1")]
    assert "_GWAY_JSON_MODE" not in os.environ


def test_entrypoint_preserves_json_mode_across_internal_resume(monkeypatch) -> None:
    observed: list[str | None] = []

    def fake_bootstrap(arguments):
        observed.append(os.environ.get("_GWAY_JSON_MODE"))
        return 0

    monkeypatch.setenv("_GWAY_JSON_MODE", "1")
    monkeypatch.setattr("gway.bootstrap.main", fake_bootstrap)

    assert entrypoint.main(["--resume", "/tmp/checkpoint.json"]) == 0
    assert observed == ["1"]
    assert os.environ["_GWAY_JSON_MODE"] == "1"


def test_global_json_mode_is_passed_to_opt_in_python_parameter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)

    monkeypatch.setenv("_GWAY_JSON_MODE", "1")
    assert dispatcher.run("json-demo", ["mode"]) == {"json": True}

    monkeypatch.setenv("_GWAY_JSON_MODE", "0")
    assert dispatcher.run("json-demo", ["mode"]) == {"json": False}


def test_explicit_function_json_option_overrides_global_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    monkeypatch.setenv("_GWAY_JSON_MODE", "1")

    assert dispatcher.run("json-demo", ["mode", "--no-json"]) == {"json": False}


def test_recipe_can_set_json_once_for_following_functions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    monkeypatch.setenv("_GWAY_JSON_MODE", "0")
    recipe = tmp_path / "json.rx"
    recipe.write_text("store --json\njson-demo mode\n", encoding="utf-8")

    assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == {"json": True}


def test_recipe_can_disable_global_json_for_following_functions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dispatcher = _dispatcher(tmp_path)
    monkeypatch.setenv("_GWAY_JSON_MODE", "1")
    recipe = tmp_path / "json-off.rx"
    recipe.write_text("store --no-json\njson-demo mode\n", encoding="utf-8")

    assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == {"json": False}
