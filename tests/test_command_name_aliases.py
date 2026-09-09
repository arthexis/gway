from __future__ import annotations

from pathlib import Path

from sigils import Sigil

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.sigils import gway_context


def _registered_dispatcher(tmp_path: Path) -> tuple[Dispatcher, GwayPaths]:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "commands.py").write_text(
        "def node_role():\n"
        "    return 'worker'\n",
        encoding="utf-8",
    )
    (root / "gway.toml").write_text(
        """[project]
name = "demo"

[adapter]
type = "python"
module = "commands"
""",
        encoding="utf-8",
    )

    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(Project.from_path(root))
    return Dispatcher(registry), paths


def test_cli_accepts_dash_and_underscore_command_spellings(tmp_path: Path) -> None:
    dispatcher, _ = _registered_dispatcher(tmp_path)

    assert dispatcher.run("demo", ["node-role"]) == "worker"
    assert dispatcher.run("demo", ["node_role"]) == "worker"


def test_sigils_accept_dash_and_underscore_command_spellings(tmp_path: Path) -> None:
    _, paths = _registered_dispatcher(tmp_path)

    assert Sigil("[demo.node-role]").solve(gway_context(paths)) == "worker"
    assert Sigil("[demo.node_role]").solve(gway_context(paths)) == "worker"
