from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
import gway.shell as shell
import gway.solve as solve_module
from gway.config import GwayPaths
from gway.solve import solve_values


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
    )


def test_solve_values_resolves_base_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert solve_values(["[cwd]"], paths=_paths(tmp_path)) == str(tmp_path)


def test_solve_values_preserves_native_type_for_exact_sigil(monkeypatch) -> None:
    monkeypatch.setattr(
        solve_module,
        "base_context",
        lambda paths=None: {"count": 5, "items": ["a", "b"], "config": {"enabled": True}},
    )

    assert solve_values(["[count]"]) == 5
    assert solve_values(["[items]"]) == ["a", "b"]
    assert solve_values(["[config]"]) == {"enabled": True}
    assert solve_values(["count=[count]"]) == "count=5"


def test_solve_values_preserves_unresolved_noninteractive(tmp_path: Path) -> None:
    assert solve_values(["before-[missing]-after"], paths=_paths(tmp_path)) == (
        "before-[missing]-after"
    )


def test_solve_values_keeps_bracket_escapes_literal(monkeypatch) -> None:
    monkeypatch.setattr(solve_module, "base_context", lambda paths=None: {"name": "Rafa"})

    assert solve_values(["[[name]]"]) == "[name]"
    assert solve_values(["left", "[-]", "right"]) == "left - right"
    assert solve_values(["Hello", "[name]"]) == "Hello Rafa"


def test_solve_values_prompts_once_per_unresolved_expression(tmp_path: Path) -> None:
    answers = {"missing": "first", "other": "second"}
    prompts: list[str] = []

    def prompt(name: str) -> str:
        prompts.append(name)
        return answers[name]

    result = solve_values(
        ["[missing]-[missing]-[other]"],
        interactive=True,
        prompt=prompt,
        paths=_paths(tmp_path),
    )

    assert result == "first-first-second"
    assert prompts == ["missing", "other"]


def test_cli_solve_passes_interactive_prompt(monkeypatch, capsys) -> None:
    observed: dict[str, object] = {}

    def fake_solve(values, *, interactive=False, prompt=None, paths=None):
        observed["values"] = values
        observed["interactive"] = interactive
        observed["prompt"] = prompt
        observed["paths"] = paths
        return "resolved"

    monkeypatch.setattr(cli, "solve_values", fake_solve)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["-i", "solve", "[missing]"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "resolved\n"
    assert observed["values"] == ["[missing]"]
    assert observed["interactive"] is True
    assert observed["prompt"] is cli._prompt_required_value


def test_cli_explicit_percent_stage_is_greedy(monkeypatch, capsys) -> None:
    observed: dict[str, object] = {}

    def fake_solve(values, *, interactive=False, prompt=None, paths=None):
        observed["values"] = tuple(values)
        return "resolved"

    monkeypatch.setattr(cli, "solve_values", fake_solve)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["%", "Battery", "at", "50", "%"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "resolved\n"
    assert observed["values"] == ("Battery", "at", "50", "%")


def test_cli_bracket_leading_stage_is_implicit_solve(monkeypatch, capsys) -> None:
    observed: dict[str, object] = {}

    def fake_solve(values, *, interactive=False, prompt=None, paths=None):
        observed["values"] = tuple(values)
        return "resolved"

    monkeypatch.setattr(cli, "solve_values", fake_solve)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["[name]", "is", "online"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "resolved\n"
    assert observed["values"] == ("[name]", "is", "online")


def test_shell_integration_adds_percent_solve_alias() -> None:
    snippet = shell.integration_snippet("bash")

    assert shell.ALIAS_LINE in snippet
    assert shell.SOLVE_ALIAS_LINE in snippet
    assert shell.SOLVE_ALIAS_LINE == "alias -- %='gway solve'"
