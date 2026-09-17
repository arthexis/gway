from pathlib import Path

import pytest

from gway.bootstrap import _normalize_command_identifiers
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher.resolution import resolve_command
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


def test_alias_argument_keys_are_normalized_case_insensitively() -> None:
    project = Project(
        name="energy",
        path=Path("."),
        adapter_type="python",
        adapter_config={},
        aliases=("OCPP",),
        alias_arguments={"OCPP": ("--mode", "Energy")},
    )

    assert project.alias_arguments == {"ocpp": ("--mode", "Energy")}


def test_managed_command_resolution_is_case_insensitive_without_changing_arguments() -> None:
    command = Command(("authorize-tag",))

    resolved, argv = resolve_command(
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


def test_cli_boundary_preserves_solve_and_expression_payload_case() -> None:
    assert _normalize_command_identifiers(("[UserName]",)) == ["[UserName]"]
    assert _normalize_command_identifiers(("Demo.Echo:=MixedCase",)) == [
        "Demo.Echo:=MixedCase"
    ]


def test_cli_boundary_finds_service_and_shell_actions_after_options() -> None:
    assert _normalize_command_identifiers(
        ("SERVICE", "--project", "OCPP", "START")
    ) == ["service", "--project", "OCPP", "start"]
    assert _normalize_command_identifiers(
        ("SHELL", "--shell", "zsh", "INSTALL")
    ) == ["shell", "--shell", "zsh", "install"]
    assert _normalize_command_identifiers(
        ("SERVICE", "--json", "START", "OCPP")
    ) == ["service", "--json", "start", "OCPP"]
