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

    project = installer.install("arthexis")

    assert project.path == checkout_target
    assert checkout_target.exists()
    assert not list(target.glob(".app.gway-*"))
    assert not (target / ".app.gway-install-lock").exists()


def test_concurrent_installer_lock_prevents_publication(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    lock = target / ".app.gway-install-lock"
    lock.mkdir(parents=True)
    installer = Installer(
        Registry(paths),
        repositories=LayoutRepositories(staging, target),
        runner=LayoutRunner(),
    )

    with pytest.raises(ValueError, match="managed checkout install already in progress"):
        installer.install("arthexis")

    assert lock.exists()
    assert not (target / "app").exists()
    assert not list(target.glob(".app.gway-*"))
    assert not staging.exists()


def test_concurrent_checkout_publication_is_not_deleted(monkeypatch, tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    target = tmp_path / "opt" / "arthexis"
    checkout_target = target / "app"
    staging = paths.projects_dir / "arthexis" / "arthexis"
    installer = Installer(
        Registry(paths),
        repositories=LayoutRepositories(staging, target),
        runner=LayoutRunner(),
    )
    original_rename = Path.rename

    def racing_rename(path: Path, destination: Path):
        if destination == checkout_target:
            checkout_target.mkdir()
            (checkout_target / "other-process").write_text(
                "owned elsewhere",
                encoding="utf-8",
            )
            raise FileExistsError(str(destination))
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", racing_rename)

    with pytest.raises(FileExistsError):
        installer.install("arthexis")

    assert (checkout_target / "other-process").read_text(encoding="utf-8") == "owned elsewhere"
    assert not list(target.glob(".app.gway-*"))
    assert not (target / ".app.gway-install-lock").exists()
    assert not staging.exists()


def test_runner_uses_manifest_environment_and_executes_hook(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "app"
    checkout.mkdir()
    environment = tmp_path / ".venv"
    python = Runner.environment_python(environment)
    python.parent.mkdir(parents=True)
    python.touch()
    project = Project(
        name="fixture",
        path=checkout,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        install_layout=InstallLayout(tmp_path, checkout, environment),
        lifecycle_hooks=LifecycleHooks(install="fixture.lifecycle:install"),
    )
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(args, **kwargs):
        calls.append(([str(value) for value in args], kwargs.get("cwd")))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)
    runner = Runner()

    assert runner.environment_path(project) == environment
    runner.run_lifecycle(replace(project, environment=environment), "install")

    command, cwd = calls[0]
    assert command[0] == str(python)
    assert command[-1] == "fixture.lifecycle:install"
    assert cwd == checkout
