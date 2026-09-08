from __future__ import annotations

from pathlib import Path

from gway.config import GwayPaths
from gway.install import Installer
from gway.lifecycle import run_hook
from gway.project import Project
from gway.registry import Registry
from gway.repository import ResolvedRepository


class ManagedRepositories:
    def __init__(self, staging: Path, managed_root: Path) -> None:
        self.staging = staging
        self.managed_root = managed_root

    def resolve(self, spec: str) -> ResolvedRepository:
        assert spec == "fixture"
        return ResolvedRepository("arthexis", "fixture")

    def clone(self, repository: ResolvedRepository) -> Path:
        checkout = self.staging / repository.name
        package = checkout / "fixture"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "commands.py").write_text(
            "def status():\n    return 'ok'\n",
            encoding="utf-8",
        )
        (checkout / "gway.toml").write_text(
            f'''[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture.commands"

[install]
root = "{self.managed_root.as_posix()}"
checkout = "app"
environment = ".venv"
''',
            encoding="utf-8",
        )
        return checkout

    def revision(self, checkout: Path) -> str:
        assert checkout == self.managed_root / "app"
        return "revision"


class RecordingRunner:
    def __init__(self) -> None:
        self.prepared: Project | None = None

    def prepare(self, project: Project) -> Path:
        self.prepared = project
        environment = project.managed_environment
        assert environment is not None
        environment.mkdir(parents=True)
        return environment


def test_install_relocates_checkout_before_environment_setup(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    managed_root = tmp_path / "opt" / "fixture"
    repositories = ManagedRepositories(tmp_path / "staging", managed_root)
    runner = RecordingRunner()

    project = Installer(registry, repositories=repositories, runner=runner).install("fixture")

    assert project.path == managed_root / "app"
    assert project.environment == managed_root / ".venv"
    assert runner.prepared is not None
    assert runner.prepared.path == managed_root / "app"
    assert registry.require("fixture").path == managed_root / "app"
    assert not (tmp_path / "staging" / "fixture").exists()


def test_lifecycle_hook_dispatches_through_project_adapter(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "gway.toml").write_text(
        '''[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture.commands"

[lifecycle]
prepare = "managed_prepare"
''',
        encoding="utf-8",
    )
    project = Project.from_path(root)
    calls: list[tuple[tuple[str, ...], list[str]]] = []

    class Adapter:
        def run(self, path, argv):
            calls.append((path, argv))
            return "prepared"

    class Adapters:
        def create(self, selected):
            assert selected == project
            return Adapter()

    monkeypatch.setattr("gway.lifecycle.AdapterRegistry", Adapters)

    assert run_hook(project, "prepare") == "prepared"
    assert calls == [(('managed_prepare',), [])]
    assert run_hook(project, "upgrade") is None
