from __future__ import annotations

from pathlib import Path

from gway.adapters import AdapterRegistry
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


class WireAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (Command(("status",), summary="Show wire status."),)

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        return {"path": path, "argv": argv}


def make_wire_dispatcher(tmp_path: Path) -> tuple[Dispatcher, Registry]:
    root = tmp_path / "wire"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "wire"
aliases = { wg = ["--protocol", "wg"], wireguard = ["--protocol", "wg"] }

[adapter]
type = "wire-test"
""",
        encoding="utf-8",
    )

    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(root)
    adapters = AdapterRegistry()
    adapters.register("wire-test", WireAdapter)
    return Dispatcher(registry, adapters), registry


def test_alias_arguments_are_persisted_in_registry(tmp_path: Path) -> None:
    _, registry = make_wire_dispatcher(tmp_path)

    project = registry.require("wg")

    assert project.aliases == ("wg", "wireguard")
    assert project.alias_arguments == {
        "wg": ("--protocol", "wg"),
        "wireguard": ("--protocol", "wg"),
    }


def test_alias_arguments_are_passed_to_downstream_command(tmp_path: Path) -> None:
    dispatcher, _ = make_wire_dispatcher(tmp_path)

    result = dispatcher.run("wg", ["status"])

    assert result == {"path": ("status",), "argv": ["--protocol", "wg"]}


def test_each_alias_can_supply_its_own_arguments(tmp_path: Path) -> None:
    dispatcher, _ = make_wire_dispatcher(tmp_path)

    result = dispatcher.run("wireguard", ["status", "--verbose"])

    assert result == {
        "path": ("status",),
        "argv": ["--protocol", "wg", "--verbose"],
    }


def test_canonical_project_name_does_not_inject_alias_arguments(tmp_path: Path) -> None:
    dispatcher, _ = make_wire_dispatcher(tmp_path)

    result = dispatcher.run("wire", ["status"])

    assert result == {"path": ("status",), "argv": []}
