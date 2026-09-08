from pathlib import Path

import pytest

from gway.adapters import AdapterRegistry
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import CommandNotFound, Dispatcher
from gway.project import Project
from gway.registry import Registry


class RequestAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (
            Command(("issue",), summary="Create an issue."),
            Command(("status",), summary="Show status."),
        )

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        return {"path": path, "argv": argv}


def make_dispatcher(tmp_path: Path, default: str = "issue") -> Dispatcher:
    root = tmp_path / "request"
    root.mkdir()
    (root / "gway.toml").write_text(
        f'''[project]
name = "request"
default = "{default}"

[adapter]
type = "request-test"
''',
        encoding="utf-8",
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(root)
    adapters = AdapterRegistry()
    adapters.register("request-test", RequestAdapter)
    return Dispatcher(registry, adapters)


def test_project_default_command_is_persisted(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert dispatcher.registry.require("request").default_command == ("issue",)


def test_unmatched_tokens_are_arguments_to_default_command(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    result = dispatcher.run("request", ["lcd", "LCD write fails"])
    assert result == {
        "path": ("issue",),
        "argv": ["lcd", "LCD write fails"],
    }


def test_explicit_command_takes_precedence_over_default(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    result = dispatcher.run("request", ["status"])
    assert result == {"path": ("status",), "argv": []}


def test_missing_configured_default_is_reported(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path, default="missing")
    with pytest.raises(CommandNotFound, match="configured default command not found: missing"):
        dispatcher.run("request", ["lcd"])
