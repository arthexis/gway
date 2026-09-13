from __future__ import annotations

import sys
from pathlib import Path

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.recipe import run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "recipe-cli-project"
    root.mkdir()
    (root / "recipe_cli_commands.py").write_text(
        """def greet(*, name: str) -> str:
    return f\"hello {name}\"


def mapping() -> dict[str, str]:
    return {\"customer\": \"cust-1\"}
""",
        encoding="utf-8",
    )
    sys.modules.pop("recipe_cli_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "recipe_cli_commands"},
        )
    )
    return Dispatcher(registry)


def test_recipe_cli_executes_and_renders_final_result(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "hello.rx"
    path.write_text("store --name Ada\ndemo greet\n", encoding="utf-8")

    assert main(["recipe", str(path)], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "hello Ada\n"


def test_recipe_cli_accepts_interactive_before_recipe(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "interactive.rx"
    path.write_text("demo greet\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda: "Ada")

    assert main(["-i", "recipe", str(path)], dispatcher=dispatcher) == 0
    captured = capsys.readouterr()
    assert captured.out == "hello Ada\n"
    assert "name:" in captured.err


def test_recipe_cli_accepts_interactive_after_recipe(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "interactive.rx"
    path.write_text("demo greet\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda: "Grace")

    assert main(["recipe", "-i", str(path)], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "hello Grace\n"


def test_recipe_cli_reports_source_line_on_failure(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "failure.rx"
    path.write_text("store --name Ada\nmissing command\n", encoding="utf-8")

    assert main(["recipe", str(path)], dispatcher=dispatcher) == 2
    assert f"{path}:2:" in capsys.readouterr().err


def test_recipe_cli_rejects_non_rx_file(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "not-recipe.txt"
    path.write_text("store --name Ada\n", encoding="utf-8")

    assert main(["recipe", str(path)], dispatcher=dispatcher) == 2
    assert ".rx extension" in capsys.readouterr().err


def test_recipe_explain_trace_contains_source_provenance(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "trace.rx"
    path.write_text("demo mapping\nresult [customer]\n", encoding="utf-8")

    with explain_scope() as trace:
        assert run_recipe(path, dispatcher) == "cust-1"

    recipe_steps = [step for step in trace if step.kind.startswith("recipe.")]
    assert any(
        step.kind == "recipe.statement.start" and step.data.get("line") == 1
        for step in recipe_steps
    )
    assert any(
        step.kind == "recipe.statement.start" and step.data.get("line") == 2
        for step in recipe_steps
    )
    assert recipe_steps[-1].kind == "recipe.result"
