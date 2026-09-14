from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "variables-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "vars"

[adapter]
type = "python"
module = "variable_commands"

[variables]
TEST_ENDPOINT = "https://manifest.example/v1/enroll"
""",
        encoding="utf-8",
    )
    (root / "variable_commands.py").write_text(
        """def show(endpoint: str = \"[TEST_ENDPOINT]\") -> str:
    return endpoint
""",
        encoding="utf-8",
    )
    sys.modules.pop("variable_commands", None)
    return Project.from_path(root)


def _dispatcher(tmp_path: Path) -> Dispatcher:
    project = _project(tmp_path)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(project)
    return Dispatcher(registry)


def test_manifest_variables_survive_registration(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    project = dispatcher.registry.require("vars")

    assert project.variables == {
        "TEST_ENDPOINT": "https://manifest.example/v1/enroll"
    }


def test_string_default_sigil_uses_manifest_variable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TEST_ENDPOINT", raising=False)
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run("vars", ["show"]) == "https://manifest.example/v1/enroll"


def test_environment_overrides_matching_manifest_variable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_ENDPOINT", "https://environment.example/v1/enroll")
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run("vars", ["show"]) == "https://environment.example/v1/enroll"


def test_explicit_argument_overrides_sigil_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_ENDPOINT", "https://environment.example/v1/enroll")
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run(
        "vars",
        ["show", "--endpoint", "https://explicit.example/v1/enroll"],
    ) == "https://explicit.example/v1/enroll"


def test_help_shows_unresolved_string_default(
    tmp_path: Path,
    capsys,
) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run("vars", ["show", "--help"]) is None
    output = capsys.readouterr().out

    assert "--endpoint" in output
    assert "default: [TEST_ENDPOINT]" in output
