from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.config import GwayPaths
from gway.install import Installer
from gway.project import InstallLayout, LifecycleHooks, Project
from gway.registry import Registry
from gway.repository import ResolvedRepository
from gway.runner import Runner


class LayoutRepositories:
    def __init__(self, staging: Path, target_root: Path) -> None:
        self.staging = staging
        self.target_root = target_root
        self.validated: list[tuple[Path, str]] = []

    def resolve(self, spec: str) -> ResolvedRepository:
        assert spec == "arthexis"
        return ResolvedRepository("arthexis", "arthexis")

    def clone(self, repository: ResolvedRepository) -> Path:
        self.staging.mkdir(parents=True)
        manifest = f"""[project]
name = "arthexis"

[adapter]
type = "python"
module = "example.gway"

[install]
root = "{self.target_root}"
checkout = "app"
environment = ".venv"

[lifecycle]
install = "example.lifecycle:install"
upgrade = "example.lifecycle:upgrade"
"""
        (self.staging / "gway.toml").write_text(manifest, encoding="utf-8")
        return self.staging

    def validate_checkout(self, checkout: Path, full_name: str) -> None:
        self.validated.append((checkout, full_name))

    def upgrade(self, checkout: Path, full_name: str) -> str:
        assert checkout == self.target_root / "app"
        assert full_name == "arthexis/arthexis"
        return "managed-revision"

    def revision(self, checkout: Path) -> str:
        assert checkout == self.target_root / "app"
        return "managed-revision"


class LayoutRunner:
    def __init__(self) -> None:
        self.prepared: list[Project] = []
        self.refreshed: list[Project] = []
        self.lifecycle: list[tuple[Project, str]] = []

    def prepare(self, project: Project) -> Path:
        self.prepared.append(project)
        assert project.install_layout is not None
        project.install_layout.environment.mkdir(parents=True)
        return project.install_layout.environment

    def refresh(self, project: Project) -> Path:
        self.refreshed.append(project)
        assert project.install_layout is not None
        project.install_layout.environment.mkdir(parents=True, exist_ok=True)
        return project.install_layout.environment

    def run_lifecycle(self, project: Project, action: str) -> None:
        self.lifecycle.append((project, action))


def test_installer_places_checkout_and_environment_from_manifest(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    registry = Registry(paths)
    runner = LayoutRunner()

    project = Installer(
        registry,
        repositories=LayoutRepositories(staging, target),
        runner=runner,
    ).install("arthexis")

    assert project.path == target / "app"
    assert project.environment == target / ".venv"
    assert project.install_layout == InstallLayout(
        root=target,
        checkout=target / "app",
        environment=target / ".venv",
    )
    assert not staging.exists()
    assert registry.require("arthexis") == project
    assert runner.lifecycle == [(project, "install")]


def test_second_install_adopts_matching_managed_checkout(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    registry = Registry(paths)
    repositories = LayoutRepositories(staging, target)
    runner = LayoutRunner()
    installer = Installer(registry, repositories=repositories, runner=runner)

    first = installer.install("arthexis")
    second = installer.install("arthexis")

    assert second.path == first.path == target / "app"
    assert second.environment == first.environment == target / ".venv"
    assert not staging.exists()
    assert repositories.validated == [(target / "app", "arthexis/arthexis")]
    assert runner.refreshed == [replace(second, environment=None)]
    assert registry.require("arthexis") == second


def test_failed_checkout_move_removes_partial_managed_destination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    installer = Installer(
        Registry(paths),
        repositories=LayoutRepositories(staging, target),
        runner=LayoutRunner(),
    )

    def fail_move(source: str, destination: str) -> None:
        assert Path(source).parent == staging
        partial = Path(destination)
        partial.write_text("incomplete", encoding="utf-8")
        raise OSError("copy failed")

    monkeypatch.setattr("gway.install.shutil.move", fail_move)

    with pytest.raises(OSError, match="copy failed"):
        installer.install("arthexis")

    assert not (target / "app").exists()
    assert not list(target.glob(".app.gway-*"))
    assert not (target / ".app.gway-install-lock").exists()
    assert not staging.exists()


def test_checkout_is_published_only_after_relocation(monkeypatch, tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    checkout_target = target / "app"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    installer = Installer(
        Registry(paths),
        repositories=LayoutRepositories(staging, target),
        runner=LayoutRunner(),
    )
    original_move = __import__("shutil").move

    def observing_move(source: str, destination: str):
        assert not checkout_target.exists()
        return original_move(source, destination)

    monkeypatch.setattr("gway.install.shutil.move", observing_move)
