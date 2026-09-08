from __future__ import annotations

from pathlib import Path

import pytest

import gway.dispatcher as dispatcher_module
from gway.adapters import AdapterRegistry
from gway.cli import main
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import CommandNotFound, Dispatcher, DispatchError
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
        )

    def describe(self, path: tuple[str, ...]) -> Command:
        for command in self.commands():
            if command.path == path:
                return command
        raise CommandNotFound(f"unknown command: {' '.join(path)}")

    def sigil_context(self, command_path: tuple[str, ...]):
        return {
            "MODEL": {
                "name": "demo",
                "command": " ".join(command_path),
            }
        }

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


def test_cli_renders_project_level_help(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fx", "--help"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out

    assert "usage: gway fixture <command> [arguments]" in output
    assert "hello" in output
    assert "Say hello." in output
    assert "peer add" in output
    assert "Add a peer." in output


def test_dispatcher_uses_longest_command_path(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fx", ["peer", "add", "gway-004"])

    assert result == {"path": ("peer", "add"), "argv": ["gway-004"]}


def test_dispatcher_resolves_project_aware_sigils(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run(
        "fx",
        [
            "peer",
            "add",
            "[project.name]",
            "[project.path]",
            "[command.path]",
            "[MODEL.name]",
        ],
    )

    assert result == {
        "path": ("peer", "add"),
        "argv": [
            "fixture",
            str((tmp_path / "fixture").resolve()),
            "peer add",
            "demo",
        ],
    }


def test_dispatcher_captures_eager_values_before_adapter_context(
    tmp_path: Path, monkeypatch
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    events: list[str] = []
    original_capture = dispatcher_module.capture_cli_values

    def capture(values, *, paths=None):
        events.append("capture")
        return original_capture(values, paths=paths)

    def context(self, command_path):
        events.append("context")
        return {"MODEL": {"name": "demo", "command": " ".join(command_path)}}

    monkeypatch.setattr(dispatcher_module, "capture_cli_values", capture)
    monkeypatch.setattr(FixtureAdapter, "sigil_context", context)

    result = dispatcher.run("fx", ["peer", "add", "%[cwd]", "[MODEL.name]"])

    assert events == ["capture", "context"]
    assert result == {
        "path": ("peer", "add"),
        "argv": [str(Path.cwd()), "demo"],
    }


def test_dispatcher_rejects_reserved_adapter_context(tmp_path: Path, monkeypatch) -> None:
    dispatcher = make_dispatcher(tmp_path)

    monkeypatch.setattr(
        FixtureAdapter,
        "sigil_context",
        lambda self, command_path: {"project": {"name": "shadowed"}},
    )

    with pytest.raises(DispatchError, match="cannot replace reserved keys: project"):
        dispatcher.run("fx", ["peer", "add", "[project.name]"])


def test_dispatcher_rejects_non_mapping_adapter_context(tmp_path: Path, monkeypatch) -> None:
    dispatcher = make_dispatcher(tmp_path)

    monkeypatch.setattr(
        FixtureAdapter,
        "sigil_context",
        lambda self, command_path: ["not", "a", "mapping"],
    )

    with pytest.raises(DispatchError, match="must return a mapping"):
        dispatcher.run("fx", ["peer", "add", "value"])
