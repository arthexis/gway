import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.config import GwayConfig, GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.repository import RepositoryError, RepositoryManager, WorkingTreeEntry
from gway.upgrade import UpgradeError, UpgradeResult, Upgrader


def test_repository_status_returns_structured_entries(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def fake_run(args, **kwargs):
        assert [str(value) for value in args] == [
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "-z",
        ]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["errors"] == "surrogateescape"
        return SimpleNamespace(
            returncode=0,
            stdout=" M src/example.py\0?? notes with spaces.txt\0",
            stderr="",
        )

    monkeypatch.setattr("gway.repository.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    assert manager.status(checkout) == (
        WorkingTreeEntry(status=" M", path="src/example.py"),
        WorkingTreeEntry(status="??", path="notes with spaces.txt"),
    )


def test_repository_status_preserves_rename_source(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    monkeypatch.setattr(
        "gway.repository.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="R  new name.py\0old name.py\0",
            stderr="",
        ),
    )
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    manager = RepositoryManager(paths, GwayConfig(("arthexis",)))

    assert manager.status(checkout) == (
        WorkingTreeEntry(
            status="R ",
            path="new name.py",
            original_path="old name.py",
        ),
    )


def test_upgrade_result_audit_fields_default_to_non_forced(tmp_path: Path) -> None:
    project = Project(
        name="fixture",
        path=tmp_path,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
    )

    result = UpgradeResult(project=project, changed=True)

    assert result.force_used is False
    assert result.force_error_type is None
    assert result.force_error is None
    assert result.dirty_files == ()


def _commit_checkout(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init", "--quiet"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "tests@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Gway Tests"],
        check=True,
    )
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "--quiet", "-m", "fixture"],
        check=True,
    )


def write_manifest(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "gway.toml").write_text(
        '''[project]
name = "wireguard"

[adapter]
type = "python"
module = "example.gway"
''',
        encoding="utf-8",
    )
    _commit_checkout(path)


def managed_project(path: Path) -> Project:
    return Project(
        name="wireguard",
        path=path,
        adapter_type="python",
        adapter_config={"module": "example.gway"},
        repository="arthexis/gway-wireguard",
        revision="old-revision",
    )


class TryForceRepositories:
    def __init__(self, *, fail_safe: bool = False, fail_force: bool = False) -> None:
        self.fail_safe = fail_safe
        self.fail_force = fail_force
        self.calls: list[bool] = []
        self.status_calls = 0
        self.current_revision = "working-revision"
        self.entries = (
            WorkingTreeEntry(status=" M", path="src/example.py"),
            WorkingTreeEntry(status="??", path="scratch.txt"),
        )

    def validate_checkout(self, checkout: Path, full_name: str) -> None:
        assert (checkout / ".git").is_dir()
        assert full_name == "arthexis/gway-wireguard"

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        self.calls.append(force)
        if not force and self.fail_safe:
            raise RepositoryError("managed checkout has local changes")
        if force and self.fail_force:
            raise RepositoryError("forced fetch failed")
        self.current_revision = "new-revision"
        return self.current_revision

    def status(self, checkout: Path) -> tuple[WorkingTreeEntry, ...]:
        self.status_calls += 1
        return self.entries

    def revision(self, checkout: Path) -> str:
        return self.current_revision

    def reset(self, checkout: Path, full_name: str, revision: str) -> None:
        return None


class FixtureRunner:
    def __init__(self, *, fail_refresh: bool = False) -> None:
        self.fail_refresh = fail_refresh

    def refresh(self, project: Project, *args, **kwargs):
        if self.fail_refresh:
            raise RuntimeError("refresh failed")
        return project.environment


def make_upgrader(tmp_path: Path, repositories, *, runner=None) -> Upgrader:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "wireguard"
    write_manifest(checkout)
    registry.register(managed_project(checkout))
    return Upgrader(
        registry,
        repositories=repositories,
        runner=runner or FixtureRunner(),
    )


def test_try_force_does_not_force_when_safe_upgrade_succeeds(tmp_path: Path) -> None:
    repositories = TryForceRepositories()
    upgrader = make_upgrader(tmp_path, repositories)

    result = upgrader.project_result("wireguard", try_force=True)

    assert repositories.calls == [False]
    assert repositories.status_calls == 0
    assert result.force_used is False
    assert result.force_error is None
    assert result.dirty_files == ()


def test_try_force_retries_repository_failure_and_captures_status(tmp_path: Path) -> None:
    repositories = TryForceRepositories(fail_safe=True)
    upgrader = make_upgrader(tmp_path, repositories)

    result = upgrader.project_result("wireguard", try_force=True)

    assert repositories.calls == [False, True]
    assert repositories.status_calls == 1
    assert result.force_used is True
    assert result.force_error_type == "RepositoryError"
    assert result.force_error == "managed checkout has local changes"
    assert result.dirty_files == repositories.entries


def test_try_force_surfaces_forced_retry_failure(tmp_path: Path) -> None:
    repositories = TryForceRepositories(fail_safe=True, fail_force=True)
    upgrader = make_upgrader(tmp_path, repositories)

    with pytest.raises(RepositoryError, match="forced fetch failed") as exc_info:
        upgrader.project_result("wireguard", try_force=True)

    assert repositories.calls == [False, True]
    assert repositories.status_calls == 1
    assert isinstance(exc_info.value.__context__, RepositoryError)
    assert str(exc_info.value.__context__) == "managed checkout has local changes"


def test_try_force_does_not_retry_post_repository_failure(tmp_path: Path) -> None:
    repositories = TryForceRepositories()
    upgrader = make_upgrader(tmp_path, repositories, runner=FixtureRunner(fail_refresh=True))

    with pytest.raises(UpgradeError, match="rollback"):
        upgrader.project_result("wireguard", try_force=True)

    assert repositories.calls == [False]
    assert repositories.status_calls == 0


def test_force_and_try_force_are_mutually_exclusive(tmp_path: Path) -> None:
    repositories = TryForceRepositories()
    upgrader = make_upgrader(tmp_path, repositories)

    with pytest.raises(UpgradeError, match="mutually exclusive"):
        upgrader.project_result("wireguard", force=True, try_force=True)

    assert repositories.calls == []
