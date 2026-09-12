from dataclasses import replace
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import ManifestError, Project
from gway.registry import Registry, RegistryError


def make_project(root: Path, *, name: str = "wireguard", aliases: str = '["wg"]') -> Path:
    root.mkdir()
    manifest = f"""[project]
name = "{name}"
aliases = {aliases}

[adapter]
type = "python"
module = "example.gway"
"""
    (root / "gway.toml").write_text(manifest, encoding="utf-8")
    return root


def test_project_manifest_is_loaded(tmp_path: Path) -> None:
    project = Project.from_path(make_project(tmp_path / "project"))
    assert project.name == "wireguard"
    assert project.aliases == ("wg",)
    assert project.adapter_type == "python"
    assert project.adapter_config == {"module": "example.gway"}
    assert project.path == (tmp_path / "project").resolve()


def test_manifest_requires_adapter(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "gway.toml").write_text('[project]\nname = "bad"\n', encoding="utf-8")
    with pytest.raises(ManifestError, match=r"requires \[adapter\]"):
        Project.from_path(root)


def test_malformed_manifest_raises_manifest_error(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "gway.toml").write_text("[project\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="invalid gway.toml"):
        Project.from_path(root)


def test_manifest_reserves_bracket_leading_project_names(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="safe directory name"):
        Project.from_path(make_project(tmp_path / "project", name="[reports]"))


def test_manifest_reserves_bracket_leading_aliases(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="aliases must not start"):
        Project.from_path(make_project(tmp_path / "project", aliases='["[reports]"]'))


def test_registry_reserves_percent_project_name(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    project = Project.from_path(make_project(tmp_path / "project", name="%", aliases="[]"))

    with pytest.raises(RegistryError, match="reserved syntax"):
        registry.register(project)


def test_registry_reserves_percent_project_alias(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    project = Project.from_path(make_project(tmp_path / "project", aliases='["%"]'))

    with pytest.raises(RegistryError, match="reserved syntax"):
        registry.register(project)


def test_registry_persists_and_resolves_aliases(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    project = registry.register_path(make_project(tmp_path / "project"))

    assert registry.require("wireguard") == project
    assert registry.require("wg") == project
    assert Registry(paths).require("wg") == project
    assert paths.state_file.is_file()


def test_registry_rejects_non_object_root(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    paths.data_dir.mkdir(parents=True)
    paths.state_file.write_text("[]\n", encoding="utf-8")

    with pytest.raises(RegistryError, match="unsupported registry format"):
        Registry(paths).list()


def test_registry_rejects_alias_collisions(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(make_project(tmp_path / "one", name="one", aliases='["shared"]'))
    with pytest.raises(RegistryError, match="already registered: shared"):
        registry.register_path(make_project(tmp_path / "two", name="two", aliases='["shared"]'))


def test_registry_reclaims_aliases_when_managed_project_is_renamed(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    old_path = make_project(tmp_path / "old", name="wireguard", aliases='["wg"]')
    old_project = replace(
        Project.from_path(old_path),
        repository="arthexis/gway-wire",
    )
    registry.register(old_project)

    new_path = make_project(
        tmp_path / "new",
        name="wire",
        aliases='["wireguard", "wg"]',
    )
    new_project = replace(
        Project.from_path(new_path),
        repository="arthexis/gway-wire",
    )

    registered = registry.register(new_project)

    assert registered == new_project
    assert registry.require("wire") == new_project
    assert registry.require("wireguard") == new_project
    assert registry.require("wg") == new_project
    assert registry.list() == [new_project]


def test_registry_does_not_reclaim_aliases_from_unrelated_repository(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    old_project = replace(
        Project.from_path(
            make_project(tmp_path / "old", name="wireguard", aliases='["wg"]')
        ),
        repository="arthexis/gway-wireguard",
    )
    registry.register(old_project)

    new_project = replace(
        Project.from_path(
            make_project(tmp_path / "new", name="wire", aliases='["wireguard", "wg"]')
        ),
        repository="other/gway-wire",
    )

    with pytest.raises(RegistryError, match="already registered"):
        registry.register(new_project)
