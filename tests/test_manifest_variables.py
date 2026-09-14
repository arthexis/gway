from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.adapters import AdapterRegistry
from gway.command import Command, Parameter
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import ManifestError, Project
from gway.registry import Registry
from gway.sigils import project_context


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


def dash(mode: str = \"-x\") -> str:
    return mode
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


def test_option_like_string_default_remains_a_value(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run("vars", ["dash"]) == "-x"


def test_manifest_variables_cannot_shadow_framework_context(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project = Project(
        **{**project.__dict__, "variables": {"cwd": "shadowed", "project": "shadowed"}}
    )

    context = project_context(project, ("show",))

    assert context["cwd"] != "shadowed"
    assert isinstance(context["project"], dict)
    assert context["project"]["name"] == "vars"


def test_manifest_rejects_non_json_variable_values(tmp_path: Path) -> None:
    root = tmp_path / "date-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "dated"

[adapter]
type = "python"
module = "commands"

[variables]
RELEASE_DATE = 2026-09-14
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="JSON-compatible"):
        Project.from_path(root)


class _FakeAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.command = Command(
            path=("show",),
            parameters=(Parameter(name="value", default="-x"),),
        )

    def commands(self) -> tuple[Command, ...]:
        return (self.command,)

    def describe(self, path: tuple[str, ...]) -> Command:
        assert path == ("show",)
        return self.command

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        assert path == ("show",)
        return argv


def test_string_default_injection_is_python_adapter_only(tmp_path: Path) -> None:
    project = Project(
        name="fake",
        path=tmp_path,
        adapter_type="fake",
        adapter_config={},
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(project)
    adapters = AdapterRegistry()
    adapters.register("fake", _FakeAdapter)
    dispatcher = Dispatcher(registry=registry, adapters=adapters)

    assert dispatcher.run("fake", ["show"]) == []
