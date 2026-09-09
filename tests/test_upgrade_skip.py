from pathlib import Path

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.upgrade import Upgrader


class Repositories:
    def __init__(self, revision: str) -> None:
        self.revision_value = revision
        self.upgrade_calls: list[tuple[Path, str, bool]] = []

    def revision(self, checkout: Path) -> str:
        return self.revision_value

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        self.upgrade_calls.append((checkout, full_name, force))
        return self.revision_value

    def reset(self, checkout: Path, full_name: str, revision: str) -> None:
        pass


class Runner:
    def __init__(self) -> None:
        self.refresh_calls: list[Project] = []

    def refresh(self, project: Project, **kwargs):
        self.refresh_calls.append(project)
        return project.environment


def registered_project(tmp_path: Path, revision: str) -> tuple[Registry, Project]:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "project"
    checkout.mkdir()
    (checkout / "gway.toml").write_text(
        '''[project]\nname = "fixture"\n\n[adapter]\ntype = "python"\nmodule = "fixture.gway"\n''',
        encoding="utf-8",
    )
    project = Project(
        name="fixture",
        path=checkout,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        repository="arthexis/gway-fixture",
        revision=revision,
    )
    return registry, registry.register(project)


def test_unchanged_revision_skips_upgrade_even_with_force(tmp_path: Path) -> None:
    revision = "a" * 40
    registry, project = registered_project(tmp_path, revision)
    repositories = Repositories(revision)
    runner = Runner()
    upgrader = Upgrader(
        registry,
        repositories=repositories,
        runner=runner,
        remote_revision=lambda checkout, full_name: revision,
    )

    result = upgrader.project_result(project.name, force=True)

    assert result.changed is False
    assert result.project == project
    assert repositories.upgrade_calls == []
    assert runner.refresh_calls == []


def test_reload_refreshes_unchanged_revision(tmp_path: Path) -> None:
    revision = "b" * 40
    registry, project = registered_project(tmp_path, revision)
    repositories = Repositories(revision)
    runner = Runner()
    upgrader = Upgrader(
        registry,
        repositories=repositories,
        runner=runner,
        remote_revision=lambda checkout, full_name: revision,
    )

    result = upgrader.project_result(project.name, reload=True)

    assert result.changed is True
    assert repositories.upgrade_calls == [
        (project.path, "arthexis/gway-fixture", False)
    ]
    assert len(runner.refresh_calls) == 1


def test_installer_arguments_refresh_unchanged_revision(tmp_path: Path) -> None:
    revision = "c" * 40
    registry, project = registered_project(tmp_path, revision)
    repositories = Repositories(revision)

    class ArgumentRunner(Runner):
        def refresh(self, project: Project, **kwargs):
            self.refresh_calls.append(project)
            assert kwargs["arguments"] == ("--role", "Control")
            return project.environment

    runner = ArgumentRunner()
    upgrader = Upgrader(
        registry,
        repositories=repositories,
        runner=runner,
        remote_revision=lambda checkout, full_name: revision,
    )

    result = upgrader.project_result(
        project.name,
        arguments=("--role", "Control"),
    )

    assert result.changed is True
    assert len(repositories.upgrade_calls) == 1
    assert len(runner.refresh_calls) == 1
