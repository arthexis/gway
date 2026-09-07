from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import ManifestError, Project
from gway.registry import Registry, RegistryError


def make_project(root: Path, *, name: str = "wireguard", aliases: str = '["wg"]') -> Path:
    root.mkdir()
    (root / "gway.toml").write_text(
        f'''[project]\nname = "{name}"\naliases = {aliases}\n\n[adapter]\ntype = "python"\nmodule = "example.gway"\n''',
        encoding="utf-8",
    )
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


def test_registry_persists_and_resolves_aliases(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    project = registry.register_path(make_project(tmp_path / "project"))

    assert registry.require("wireguard") == project
    assert registry.require("wg") == project
    assert Registry(paths).require("wg") == project
    assert paths.state_file.is_file()


def test_registry_rejects_alias_collisions(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(make_project(tmp_path / "one", name="one", aliases='["shared"]'))
    with pytest.raises(RegistryError, match="already registered: shared"):
        registry.register_path(make_project(tmp_path / "two", name="two", aliases='["shared"]'))
