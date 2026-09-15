from __future__ import annotations

import sys
from pathlib import Path

import gway.entrypoint as entrypoint
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.output_context import current_json_mode, json_mode_scope, seed_legacy_cli_json_mode
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


def consume(*, json: bool = False) -> str:
    return "json" if json else "plain"
""",
        encoding="utf-8",
    )
    sys.modules.pop("commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(Project.from_path(root))
    return Dispatcher(registry)


def test_entrypoint_scopes_global_json_mode_without_leaking(monkeypatch) -> None:
    observed: list[tuple[list[str], bool | None]] = []

    def fake_bootstrap(arguments):
        observed.append((list(arguments), current_json_mode()))
        return 0

    monkeypatch.setattr("gway.bootstrap.main", fake_bootstrap)

    assert current_json_mode() is None
    assert entrypoint.main(["--json", "list"]) == 0
    assert observed == [(["--json", "list"], True)]
    assert current_json_mode() is None


def test_legacy_launcher_seed_uses_invocation_local_context() -> None:
    with json_mode_scope(False):
        assert current_json_mode() is False
        seed_legacy_cli_json_mode(["--json", "list"])
        assert current_json_mode() is True
    assert current_json_mode() is None


def test_global_json_mode_is_passed_to_opt_in_python_parameter(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    with json_mode_scope(True):
        assert dispatcher.run("json-demo", ["consume"]) == "json"

    with json_mode_scope(False):
        assert dispatcher.run("json-demo", ["consume"]) == "plain"


def test_explicit_function_json_option_overrides_global_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    with json_mode_scope(True):
        assert dispatcher.run("json-demo", ["consume", "--no-json"]) == "plain"


def test_function_json_argument_does_not_mutate_recipe_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "isolated-json.rx"
    recipe.write_text(
        "json-demo consume --json\njson-demo consume\n",
        encoding="utf-8",
    )

    with json_mode_scope(False):
        assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == "plain"


def test_json_field_in_mapping_result_can_update_recipe_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "published-json.rx"
    recipe.write_text(
        "json-demo mode --json\njson-demo consume\n",
        encoding="utf-8",
    )

    with json_mode_scope(False):
        assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == "json"


def test_recipe_can_set_json_once_for_following_functions(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "json.rx"
    recipe.write_text("store --json\njson-demo consume\n", encoding="utf-8")

    with json_mode_scope(False):
        assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == "json"


def test_recipe_can_disable_global_json_for_following_functions(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    recipe = tmp_path / "json-off.rx"
    recipe.write_text("store --no-json\njson-demo consume\n", encoding="utf-8")

    with json_mode_scope(True):
        assert GwayRuntime(dispatcher).execute(["recipe", str(recipe)]) == "plain"
