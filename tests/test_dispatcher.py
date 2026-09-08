from __future__ import annotations

import json
import os
from pathlib import Path

from gway.adapters import AdapterRegistry
from gway.cli import main
from gway.command import Command, Parameter
from gway.config import GwayPaths
from gway.dispatcher import CommandNotFound, Dispatcher
from gway.project import Project
from gway.registry import Registry


class FixtureAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (
            Command(("hello",), summary="Say hello."),
            Command(("peer",), summary="Peer namespace fallback."),
            Command(("peer", "add"), summary="Add a peer."),
            Command(
                ("token", "create"),
                summary="Create a token for one device.",
                parameters=(
                    Parameter(
                        "device_name",
                        required=True,
                        positional=False,
                        annotation=str,
                    ),
                ),
            ),
            Command(
                ("server", "status"),
                summary=(
                    "Show deployed gateway, registry, enrollment, and DNS status without "
                    "letting wrapped text run underneath command names."
                ),
            ),
        )

    def describe(self, path: tuple[str, ...]) -> Command:
        for command in self.commands():
            if command.path == path:
                return command
        raise CommandNotFound(f"unknown command: {' '.join(path)}")

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        if path == ("hello",):
            return "hello"
        return {"path": path, "argv": argv}


def make_dispatcher(tmp_path: Path) -> Dispatcher:
    project_root = tmp_path / "fixture"
    project_root.mkdir()
    (project_root / "gway.toml").write_text(
        """[project]
name = "fixture"
aliases = ["fx"]

[adapter]
type = "fixture"
""",
        encoding="utf-8",
    )

    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(project_root)
    adapters = AdapterRegistry()
    adapters.register("fixture", FixtureAdapter)
    return Dispatcher(registry, adapters)


def test_cli_dispatches_registered_project(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fixture", "hello"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "hello\n"


def test_cli_interactive_prompts_for_missing_required_option(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    answers = iter(["gway-004"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    assert main(["-i", "fixture", "token", "create"], dispatcher=dispatcher) == 0

    captured = capsys.readouterr()
    assert "device_name: " in captured.err
    assert "--device-name" in captured.out
    assert "gway-004" in captured.out


def test_json_interactive_prompt_does_not_pollute_stdout(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    monkeypatch.setattr("builtins.input", lambda: "gway-004")

    assert main(["--json", "-i", "fixture", "token", "create"], dispatcher=dispatcher) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["argv"] == ["--device-name", "gway-004"]
    assert "device_name: " in captured.err


def test_cli_renders_project_level_help(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fx", "--help"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out

    assert "usage: gway fixture <command> [arguments]" in output
    assert "hello" in output
    assert "Say hello." in output
    assert "peer add" in output
    assert "Add a peer." in output


def test_cli_wraps_help_descriptions_in_right_column(tmp_path: Path, monkeypatch, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)
    monkeypatch.setattr(
        "gway.cli.shutil.get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((58, 24)),
    )

    assert main(["fixture", "--help"], dispatcher=dispatcher) == 0
    lines = capsys.readouterr().out.splitlines()

    status_line = next(line for line in lines if line.startswith("  server status"))
    continuation_index = lines.index(status_line) + 1
    continuation = lines[continuation_index]
    description_column = status_line.index("Show")

    assert len(status_line) <= 58
    assert continuation.startswith(" " * description_column)
    assert continuation.strip()
    assert len(continuation) <= 58


def test_cli_help_stays_within_narrow_terminal(tmp_path: Path, monkeypatch, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)
    monkeypatch.setattr(
        "gway.cli.shutil.get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((32, 24)),
    )

    assert main(["fixture", "--help"], dispatcher=dispatcher) == 0
    command_lines = capsys.readouterr().out.split("commands:\n", 1)[1].splitlines()
    assert command_lines
    assert all(len(line) <= 32 for line in command_lines)


def test_dispatcher_uses_longest_command_path(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fx", ["peer", "add", "gway-004"])

    assert result == {"path": ("peer", "add"), "argv": ["gway-004"]}


def test_dispatcher_resolves_project_aware_sigils(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run(
        "fx",
        ["peer", "add", "[project.name]", "[project.path]", "[command.path]"],
    )

    assert result == {
        "path": ("peer", "add"),
        "argv": ["fixture", str((tmp_path / "fixture").resolve()), "peer add"],
    }
