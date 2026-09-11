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
        "def node_role():\n    return 'worker'\n"
        "\n"
        "def start_server():\n    return 'started'\n"
        "\n"
        "def alpha_beta():\n    return 'alpha-beta'\n"
        "\n"
        "def beta_alpha():\n    return 'beta-alpha'\n",
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


def test_cli_accepts_reversed_two_word_command_spelling(tmp_path: Path) -> None:
    dispatcher, _ = _registered_dispatcher(tmp_path)

    assert dispatcher.run("demo", ["start-server"]) == "started"
    assert dispatcher.run("demo", ["start_server"]) == "started"
    assert dispatcher.run("demo", ["server-start"]) == "started"
    assert dispatcher.run("demo", ["server_start"]) == "started"


def test_sigils_accept_reversed_two_word_command_spelling(tmp_path: Path) -> None:
    _, paths = _registered_dispatcher(tmp_path)

    context = gway_context(paths)
    assert Sigil("[demo.start-server]").solve(context) == "started"
    assert Sigil("[demo.start_server]").solve(context) == "started"
    assert Sigil("[demo.server-start]").solve(context) == "started"
    assert Sigil("[demo.server_start]").solve(context) == "started"


def test_exact_two_word_command_spelling_wins_over_reversed_alias(tmp_path: Path) -> None:
    dispatcher, paths = _registered_dispatcher(tmp_path)

    assert dispatcher.run("demo", ["alpha-beta"]) == "alpha-beta"
    assert dispatcher.run("demo", ["beta-alpha"]) == "beta-alpha"

    context = gway_context(paths)
    assert Sigil("[demo.alpha-beta]").solve(context) == "alpha-beta"
    assert Sigil("[demo.beta-alpha]").solve(context) == "beta-alpha"
