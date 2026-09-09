from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.cli import main
from gway.config import GwayConfig, GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.repository import RepositoryError, RepositoryManager
from gway.runner import Runner
from gway.upgrade import UpgradeError, Upgrader


class FixtureRepositories:
    def __init__(self, revision: str = "new-revision") -> None:
        self.revision = revision
        self.calls: list[tuple[Path, str, bool]] = []

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        self.calls.append((checkout, full_name, force))
        return self.revision


class FixtureRunner:
    def __init__(self) -> None:
        self.calls: list[Project] = []

    def refresh(self, project: Project) -> Path | None:
        self.calls.append(project)
        return project.environment


def write_manifest(path: Path, *, name: str = "wireguard", alias: str = "wg") -> None:
    path.mkdir(parents=True, exist_ok=True)
    manifest = f'''[project]
name = "{name}"
aliases = ["{alias}"]

[adapter]
type = "python"
module = "example.gway"
'''
    (path / "gway.toml").write_text(manifest, encoding="utf-8")


def managed_project(path: Path, environment: Path | None = None) -> Project:
    return Project(
        name="wireguard",
        aliases=("old-wg",),
        path=path,
        adapter_type="python",
        adapter_config={"module": "old.gway"},
        repository="arthexis/gway-wireguard",
        revision="old-revision",
        environment=environment,
    )


def test_project_upgrade_refreshes_manifest_environment_and_registry(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "wireguard"
    environment = paths.environments_dir / "wireguard"
    write_manifest(checkout)
    registry.register(managed_project(checkout, environment))
    repositories = FixtureRepositories()
    runner = FixtureRunner()

    project = Upgrader(registry, repositories=repositories, runner=runner).project("old-wg")

    assert project.revision == "new-revision"
    assert project.aliases == ("wg",)
    assert project.adapter_config == {"module": "example.gway"}
    assert project.environment == environment
    assert registry.require("wg") == project
    assert repositories.calls == [(checkout, "arthexis/gway-wireguard", False)]
    assert runner.calls == [project]


def test_project_upgrade_propagates_force(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "wireguard"
    write_manifest(checkout)
    registry.register(managed_project(checkout))
    repositories = FixtureRepositories()

    Upgrader(
        registry,
        repositories=repositories,
        runner=FixtureRunner(),
    ).project("wireguard", force=True)

    assert repositories.calls == [(checkout, "arthexis/gway-wireguard", True)]


def test_project_upgrade_rejects_local_registration(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "local"
    write_manifest(checkout, name="local", alias="loc")
    registry.register(Project.from_path(checkout))

    with pytest.raises(UpgradeError, match="locally registered"):
        Upgrader(registry, repositories=FixtureRepositories(), runner=FixtureRunner()).project(
            "local",
            force=True,
        )


def test_all_projects_skips_local_registrations(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    managed = tmp_path / "managed"
    local = tmp_path / "local"
    write_manifest(managed)
    write_manifest(local, name="local", alias="loc")
    registry.register(managed_project(managed))
    registry.register(Project.from_path(local))
    repositories = FixtureRepositories()

    upgraded = Upgrader(
        registry,
        repositories=repositories,
        runner=FixtureRunner(),
    ).all_projects(force=True)

    assert [project.name for project in upgraded] == ["wireguard"]
    assert repositories.calls == [(managed, "arthexis/gway-wireguard", True)]


def test_self_upgrade_uses_current_python_and_forces_reinstall(monkeypatch) -> None:
    calls: list[tuple[list[str], bool, object]] = []

    def fake_run(args, *, check, stdout=None):
        calls.append(([str(value) for value in args], check, stdout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.upgrade.subprocess.run", fake_run)

    Upgrader.upgrade_self("git+https://example.invalid/gway.git@main")

    assert calls == [
        (
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--upgrade",
                "--force-reinstall",
                "git+https://example.invalid/gway.git@main",
            ],
            True,
            sys.stderr,
        )
    ]


def test_repository_upgrade_requires_clean_matching_checkout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        command = [str(value) for value in args]
        calls.append(command)
        if "status" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "get-url" in command:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/arthexis/gway-wireguard.git\n",
                stderr="",
            )
        if "symbolic-ref" in command:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if "pull" in command:
            return SimpleNamespace(returncode=0, stdout="Already up to date.\n", stderr="")
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout="abcdef\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    revision = manager.upgrade(checkout, "arthexis/gway-wireguard")

    assert revision == "abcdef"
    assert any(command[-2:] == ["pull", "--ff-only"] for command in calls)


def test_repository_upgrade_rejects_dirty_checkout(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def fake_run(args, **kwargs):
        command = [str(value) for value in args]
        if "status" in command:
            return SimpleNamespace(returncode=0, stdout=" M file.py\n", stderr="")
        if "get-url" in command:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/arthexis/gway-wireguard.git\n",
                stderr="",
            )
        if "symbolic-ref" in command:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    with pytest.raises(RepositoryError, match="local changes"):
        manager.upgrade(checkout, "arthexis/gway-wireguard")


def test_repository_force_resets_dirty_checkout_to_trusted_upstream(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        command = [str(value) for value in args]
        calls.append(command)
        if "status" in command:
            return SimpleNamespace(
                returncode=0,
                stdout=" M file.py\n?? scratch/\n",
                stderr="",
            )
        if "get-url" in command:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/arthexis/gway-wireguard.git\n",
                stderr="",
            )
        if "symbolic-ref" in command:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if any(value in command for value in ("fetch", "reset", "clean")):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout="fedcba\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    revision = manager.upgrade(checkout, "arthexis/gway-wireguard", force=True)

    assert revision == "fedcba"
    assert ["git", "-C", str(checkout), "fetch", "--prune", "origin"] in calls
    assert ["git", "-C", str(checkout), "reset", "--hard", "origin/main"] in calls
    assert ["git", "-C", str(checkout), "clean", "-fd"] in calls
    assert not any("pull" in command for command in calls)


def test_repository_force_validates_origin_before_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        command = [str(value) for value in args]
        calls.append(command)
        if "status" in command:
            return SimpleNamespace(returncode=0, stdout=" M file.py\n", stderr="")
        if "get-url" in command:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/example/other.git\n",
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    with pytest.raises(RepositoryError, match="origin does not match"):
        manager.upgrade(checkout, "arthexis/gway-wireguard", force=True)

    mutating = ("fetch", "reset", "clean")
    assert not any(any(value in command for value in mutating) for command in calls)


def test_runner_refresh_reinstalls_project_without_editable_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    environment = tmp_path / "environment"
    python = Runner.environment_python(environment)
    python.parent.mkdir(parents=True)
    python.touch()
    project = Project(
        name="fixture",
        path=root,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        environment=environment,
    )
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append([str(value) for value in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)

    refreshed = Runner().refresh(project)

    assert refreshed == environment
    assert calls[0][0] == str(python)
    assert "--upgrade" in calls[0]
    assert "-e" not in calls[0]
    assert calls[0][-1] == str(root)


def test_cli_upgrade_modes(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "data"))
    calls: list[str] = []
    project = Project(
        name="wireguard",
        path=tmp_path / "wireguard",
        adapter_type="python",
        adapter_config={"module": "example.gway"},
        repository="arthexis/gway-wireguard",
        revision="abcdef",
    )

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def project_result(
            self,
            name: str,
            *,
            force: bool = False,
            reload: bool = False,
            arguments=(),
        ):
            calls.append(f"project:{name}:force={force}")
            return SimpleNamespace(project=project, changed=True)

        def all_project_results(self, *, force: bool = False, reload: bool = False):
            calls.append(f"all:force={force}")
            return [SimpleNamespace(project=project, changed=True)]

        def project(self, name: str, *, force: bool = False) -> Project:
            calls.append(f"project:{name}:force={force}")
            return project

        def all_projects(self, *, force: bool = False) -> list[Project]:
            calls.append(f"all:force={force}")
            return [project]

        def upgrade_self(self) -> None:
            calls.append("self")

    monkeypatch.setattr("gway.cli.Upgrader", FakeUpgrader)

    assert main(["upgrade", "wireguard"]) == 0
    assert calls == ["project:wireguard:force=False"]
    calls.clear()
    capsys.readouterr()

    assert main(["upgrade", "wireguard", "--force"]) == 0
    assert calls == ["project:wireguard:force=True"]
    calls.clear()
    capsys.readouterr()

    assert main(["upgrade", "--all", "--force"]) == 0
    assert calls == ["all:force=True"]
    calls.clear()
    capsys.readouterr()

    assert main(["upgrade", "--self"]) == 0
    assert calls == ["self"]
    calls.clear()
    capsys.readouterr()

    assert main(["upgrade", "--force"]) == 0
    assert calls == ["self", "all:force=True"]
