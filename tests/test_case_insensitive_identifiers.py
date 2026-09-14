from pathlib import Path

import pytest

from gway.bootstrap import _normalize_command_identifiers
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry, RegistryError
from gway.stage import classify_stage


def make_project(root: Path, *, name: str, aliases: str) -> Path:
    root.mkdir()
    (root / "gway.toml").write_text(
        f'''[project]\nname = "{name}"\naliases = {aliases}\n\n[adapter]\ntype = "python"\nmodule = "example.gway"\n''',
        encoding="utf-8",
    )
    return root


def test_registry_resolves_project_names_and_aliases_case_insensitively(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    project = registry.register_path(
        make_project(tmp_path / "project", name="energy", aliases='["ocpp"]')
    )

    assert registry.require("ENERGY") == project
    assert registry.require("Energy") == project
    assert registry.require("OCPP") == project
    assert Registry(paths).require("OcPp") == project


def test_registry_rejects_case_only_alias_duplicates(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    project = Project.from_path(
        make_project(tmp_path / "project", name="energy", aliases='["ocpp", "OCPP"]')
    )

    with pytest.raises(RegistryError, match="duplicate name or alias"):
        registry.register(project)


def test_registry_rejects_case_only_collisions_between_projects(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(
        make_project(tmp_path / "one", name="one", aliases='["Energy"]')
    )

    with pytest.raises(RegistryError, match="already registered: energy"):
        registry.register_path(
            make_project(tmp_path / "two", name="two", aliases='["energy"]')
        )


def test_managed_command_resolution_is_case_insensitive_without_changing_arguments() -> None:
    command = Command(("authorize-tag",))

    resolved, argv = Dispatcher._resolve_command(
        (command,),
        ("AUTHORIZE_TAG", "Tag-With-Mixed-Case"),
    )

    assert resolved == command
    assert argv == ["Tag-With-Mixed-Case"]


def test_stage_normalizes_only_the_project_or_operation_identifier() -> None:
    stage = classify_stage(("OCPP", "AUTHORIZE", "Tag-With-Mixed-Case"))

    assert stage.tokens == ("ocpp", "AUTHORIZE", "Tag-With-Mixed-Case")
    assert stage.raw_tokens == ("OCPP", "AUTHORIZE", "Tag-With-Mixed-Case")


def test_cli_boundary_normalizes_core_actions_without_changing_values() -> None:
    assert _normalize_command_identifiers(
        ("--json", "SERVICE", "START", "OCPP")
    ) == ["--json", "service", "start", "OCPP"]
    assert _normalize_command_identifiers(
        ("OCPP", "AUTHORIZE", "Tag-With-Mixed-Case")
    ) == ["ocpp", "AUTHORIZE", "Tag-With-Mixed-Case"]
