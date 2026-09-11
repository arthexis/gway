from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from gway.config import GwayPaths
from gway.install import Installer
from gway.project import Project
from gway.registry import Registry


def write_manifest(path: Path, *, name: str, aliases: tuple[str, ...] = ()) -> None:
    path.mkdir(parents=True, exist_ok=True)
    alias_text = ", ".join(f'"{alias}"' for alias in aliases)
    (path / "gway.toml").write_text(
        f'[project]\nname = "{name}"\naliases = [{alias_text}]\n\n'
        '[adapter]\ntype = "python"\nmodule = "example.gway"\n',
        encoding="utf-8",
    )


def test_uninstall_removes_managed_checkout_environment_and_registry(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = paths.projects_dir / "arthexis" / "gway-fixture"
    environment = paths.environments_dir / "fixture"
    write_manifest(checkout, name="fixture", aliases=("fx",))
    environment.mkdir(parents=True)
    project = replace(
        Project.from_path(checkout),
        repository="arthexis/gway-fixture",
        environment=environment,
    )
    registry.register(project)

    removed = Installer(registry).uninstall("fx")

    assert removed.name == "fixture"
    assert registry.get("fixture") is None
    assert not checkout.exists()
    assert not environment.exists()


def test_uninstall_resolves_current_name_after_project_was_renamed(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = paths.projects_dir / "arthexis" / "gway-wire"
    environment = paths.environments_dir / "wireguard"

    write_manifest(checkout, name="wireguard", aliases=("wg",))
    environment.mkdir(parents=True)
    old_project = replace(
        Project.from_path(checkout),
        repository="arthexis/gway-wire",
        environment=environment,
    )
    registry.register(old_project)

    write_manifest(checkout, name="wire", aliases=("wireguard", "wg"))

    removed = Installer(registry).uninstall("wire")

    assert removed.name == "wireguard"
    assert registry.get("wireguard") is None
    assert not checkout.exists()
    assert not environment.exists()


def test_uninstall_local_registration_keeps_source_tree(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "local-project"
    write_manifest(checkout, name="local")
    registry.register_path(checkout)

    Installer(registry).uninstall("local")

    assert checkout.exists()
    assert registry.get("local") is None
