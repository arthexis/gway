from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gway.adapters import AdapterRegistry
from gway.api import Gway
from gway.cli import main
from gway.command import Command
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
            Command(("peer-add",), summary="Kebab-case command."),
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

    def invoke(
        self,
        path: tuple[str, ...],
        args: tuple[object, ...],
        kwargs: Mapping[str, object],
    ) -> object:
        return {"path": path, "args": args, "kwargs": dict(kwargs)}


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


def test_dispatcher_uses_longest_command_path(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fx", ["peer", "add", "gway-004"])

    assert result == {"path": ("peer", "add"), "argv": ["gway-004"]}


def test_python_facade_invokes_native_arguments(tmp_path: Path) -> None:
    gw = Gway(make_dispatcher(tmp_path))

    result = gw.fixture.peer.add("gway-004", enabled=True)

    assert result == {
        "path": ("peer", "add"),
        "args": ("gway-004",),
        "kwargs": {"enabled": True},
    }


def test_python_facade_converts_underscores_in_command_names(tmp_path: Path) -> None:
    gw = Gway(make_dispatcher(tmp_path))

    result = gw.fixture.peer_add()

    assert result["path"] == ("peer-add",)
