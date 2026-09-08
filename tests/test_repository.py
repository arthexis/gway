from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.config import GwayConfig, GwayPaths
from gway.project import Project
from gway.repository import RepositoryManager, ResolvedRepository
from gway.runner import Runner


def test_short_name_prefers_gway_repository(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    repository = manager.resolve("wireguard")

    assert repository.full_name == "arthexis/gway-wireguard"
    assert calls[0][3] == "https://github.com/arthexis/gway-wireguard.git"


def test_short_name_fallback_disables_git_terminal_prompt(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0 if "arthexis/arthexis.git" in args else 2)

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    repository = manager.resolve("arthexis")

    assert repository.full_name == "arthexis/arthexis"
    assert [call[0][3] for call in calls] == [
        "https://github.com/arthexis/gway-arthexis.git",
        "https://github.com/arthexis/arthexis.git",
    ]
    assert all(call[1]["env"]["GIT_TERMINAL_PROMPT"] == "0" for call in calls)


def test_explicit_repository_uses_trusted_owner(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    repository = manager.resolve("arthexis/example")

    assert repository.full_name == "arthexis/example"
    assert repository.clone_url == "https://github.com/arthexis/example.git"


def test_checkouts_are_namespaced_by_owner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "gway.repository.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis", "example")))

    first = manager.clone(ResolvedRepository("arthexis", "shared"))
    second = manager.clone(ResolvedRepository("example", "shared"))

    assert first == paths.projects_dir / "arthexis" / "shared"
    assert second == paths.projects_dir / "example" / "shared"


def test_project_name_must_be_safe_directory_segment(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe directory name"):
        Project(
            name="../escape",
            path=tmp_path,
            adapter_type="python",
            adapter_config={"module": "fixture.gway"},
        )


def test_runner_creates_python_environment_and_installs_project(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    project = Project(
        name="fixture",
        path=root,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
    )
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append([str(value) for value in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")

    environment = Runner(paths).prepare(project)

    assert environment == paths.environments_dir / "fixture"
    assert calls[0][1:3] == ["-m", "venv"]
    assert calls[1][-2:] == ["-e", str(root)]
