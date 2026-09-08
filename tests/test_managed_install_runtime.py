from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
