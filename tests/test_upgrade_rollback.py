from __future__ import annotations

from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.upgrade import Upgrader


def write_manifest(path: Path, *, lifecycle: bool = False) -> None:
    hooks = ""
    if lifecycle:
        hooks = """
[lifecycle]
upgrade = "example.lifecycle:upgrade"
"""
    path.mkdir(parents=True, exist_ok=True)
    (path / "gway.toml").write_text(
        f"""[project]
name = "fixture"

[adapter]
type = "python"
module = "example.gway"
{hooks}
""",
        encoding="utf-8",
    )


class RollbackRepositories:
    def __init__(self) -> None:
        self.resets: list[tuple[Path, str, str]] = []

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        return "new-revision"

    def reset(self, checkout: Path, full_name: str, revision: str) -> None:
        self.resets.append((checkout, full_name, revision))


class RefreshFailsOnce:
    def __init__(self, environment: Path) -> None:
        self.environment = environment
        self.calls = 0

    def refresh(self, project: Project) -> Path:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("refresh failed")
        return self.environment


class LifecycleFails:
    def __init__(self, environment: Path) -> None:
        self.environment = environment
        self.refreshes = 0

    def refresh(self, project: Project) -> Path:
        self.refreshes += 1
        return self.environment

    def run_lifecycle(self, project: Project, action: str) -> None:
        raise RuntimeError("lifecycle failed")


def registered_project(checkout: Path, environment: Path) -> Project:
    return Project(
        name="fixture",
        path=checkout,
        adapter_type="python",
        adapter_config={"module": "example.gway"},
        repository="arthexis/gway-fixture",
        revision="old-revision",
        environment=environment,
    )


def test_refresh_failure_restores_previous_revision_and_registry(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "fixture"
    environment = tmp_path / "environment"
    write_manifest(checkout)
    current = registry.register(registered_project(checkout, environment))
    repositories = RollbackRepositories()
    runner = RefreshFailsOnce(environment)

    with pytest.raises(RuntimeError, match="refresh failed"):
        Upgrader(registry, repositories=repositories, runner=runner).project("fixture")

    assert repositories.resets == [(checkout, "arthexis/gway-fixture", "old-revision")]
    assert runner.calls == 2
    assert registry.require("fixture") == current


def test_lifecycle_failure_restores_previous_revision_and_environment(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "fixture"
    environment = tmp_path / "environment"
    write_manifest(checkout, lifecycle=True)
    current = registry.register(registered_project(checkout, environment))
    repositories = RollbackRepositories()
    runner = LifecycleFails(environment)

    with pytest.raises(RuntimeError, match="lifecycle failed"):
        Upgrader(registry, repositories=repositories, runner=runner).project("fixture")

    assert repositories.resets == [(checkout, "arthexis/gway-fixture", "old-revision")]
    assert runner.refreshes == 2
    assert registry.require("fixture") == current
