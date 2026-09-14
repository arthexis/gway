import json
import logging
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry
from gway.repository import RepositoryError, WorkingTreeEntry
from gway.upgrade import Upgrader
from gway.upgrade_history import UpgradeHistoryRecord, append_upgrade_history


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


def managed_project(path: Path) -> Project:
    return Project(
        name="wireguard",
        path=path,
        adapter_type="python",
        adapter_config={"module": "example.gway"},
        repository="arthexis/gway-wireguard",
        revision="old-revision",
    )


class HistoryRepositories:
    def __init__(self, *, fail_force: bool = False) -> None:
        self.fail_force = fail_force
        self.calls: list[bool] = []
        self.current_revision = "working-revision"
        self.entries = (
            WorkingTreeEntry(status=" M", path="src/example.py"),
            WorkingTreeEntry(status="??", path="scratch file.txt"),
        )

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        self.calls.append(force)
        if not force:
            raise RepositoryError("managed checkout has local changes")
        if self.fail_force:
            raise RepositoryError("forced fetch failed")
        self.current_revision = "new-revision"
        return self.current_revision

    def status(self, checkout: Path) -> tuple[WorkingTreeEntry, ...]:
        return self.entries

    def revision(self, checkout: Path) -> str:
        return self.current_revision

    def reset(self, checkout: Path, full_name: str, revision: str) -> None:
        return None


class CleanRepositories(HistoryRepositories):
    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        self.calls.append(force)
        self.current_revision = "new-revision"
        return self.current_revision


class FixtureRunner:
    def refresh(self, project: Project, *args, **kwargs):
        return project.environment


def make_upgrader(tmp_path: Path, repositories) -> tuple[Upgrader, GwayPaths]:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    checkout = tmp_path / "wireguard"
    write_manifest(checkout)
    registry.register(managed_project(checkout))
    return Upgrader(registry, repositories=repositories, runner=FixtureRunner()), paths


def read_history(paths: GwayPaths) -> list[dict[str, object]]:
    history = paths.data_dir / "upgrade-history.jsonl"
    return [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()]


def test_append_upgrade_history_is_append_only(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    entry = WorkingTreeEntry(status=" M", path="src/example.py")
    first = UpgradeHistoryRecord.create(
        project="one",
        repository="arthexis/gway-one",
        checkout=tmp_path / "one",
        previous_revision="aaa",
        resulting_revision="bbb",
        force_error_type="RepositoryError",
        force_error="dirty",
        forced_retry_succeeded=True,
        dirty_files=(entry,),
    )
    second = UpgradeHistoryRecord.create(
        project="two",
        repository="arthexis/gway-two",
        checkout=tmp_path / "two",
        previous_revision="ccc",
        resulting_revision=None,
        force_error_type="RepositoryError",
        force_error="dirty",
        forced_retry_succeeded=False,
    )

    append_upgrade_history(paths, first)
    append_upgrade_history(paths, second)

    records = read_history(paths)
    assert [record["project"] for record in records] == ["one", "two"]
    assert records[0]["dirty_files"] == [
        {"status": " M", "path": "src/example.py", "original_path": None}
    ]


def test_try_force_success_records_pre_force_state(tmp_path: Path) -> None:
    repositories = HistoryRepositories()
    upgrader, paths = make_upgrader(tmp_path, repositories)

    result = upgrader.project_result("wireguard", try_force=True)

    assert result.force_used is True
    records = read_history(paths)
    assert len(records) == 1
    record = records[0]
    assert record["project"] == "wireguard"
    assert record["repository"] == "arthexis/gway-wireguard"
    assert record["previous_revision"] == "working-revision"
    assert record["resulting_revision"] == "new-revision"
    assert record["force_used"] is True
    assert record["force_error_type"] == "RepositoryError"
    assert record["force_error"] == "managed checkout has local changes"
    assert record["forced_retry_succeeded"] is True
    assert record["dirty_files"] == [
        {"status": " M", "path": "src/example.py", "original_path": None},
        {"status": "??", "path": "scratch file.txt", "original_path": None},
    ]
    assert str(record["timestamp"]).endswith("Z")


def test_try_force_failure_records_first_error_and_no_result_revision(tmp_path: Path) -> None:
    repositories = HistoryRepositories(fail_force=True)
    upgrader, paths = make_upgrader(tmp_path, repositories)

    with pytest.raises(RepositoryError, match="forced fetch failed") as exc_info:
        upgrader.project_result("wireguard", try_force=True)

    assert isinstance(exc_info.value.__cause__, RepositoryError)
    assert str(exc_info.value.__cause__) == "managed checkout has local changes"
    record = read_history(paths)[0]
    assert record["previous_revision"] == "working-revision"
    assert record["resulting_revision"] is None
    assert record["forced_retry_succeeded"] is False
    assert record["force_error"] == "managed checkout has local changes"


def test_safe_try_force_upgrade_does_not_create_history(tmp_path: Path) -> None:
    repositories = CleanRepositories()
    upgrader, paths = make_upgrader(tmp_path, repositories)

    upgrader.project_result("wireguard", try_force=True)

    assert repositories.calls == [False]
    assert not (paths.data_dir / "upgrade-history.jsonl").exists()


def test_history_write_failure_does_not_hide_success(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    repositories = HistoryRepositories()
    upgrader, _ = make_upgrader(tmp_path, repositories)

    def fail_history(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("gway.upgrade.append_upgrade_history", fail_history)

    with caplog.at_level(logging.WARNING, logger="gway.upgrade"):
        result = upgrader.project_result("wireguard", try_force=True)

    assert "cannot append forced-upgrade history" in caplog.text
    assert result.force_used is True
    assert result.project.revision == "new-revision"


def test_history_permission_failure_is_preserved(monkeypatch, tmp_path: Path) -> None:
    repositories = HistoryRepositories()
    upgrader, _ = make_upgrader(tmp_path, repositories)

    def fail_history(*args, **kwargs):
        raise PermissionError("history denied")

    monkeypatch.setattr("gway.upgrade.append_upgrade_history", fail_history)

    with pytest.raises(PermissionError, match="history denied"):
        upgrader.project_result("wireguard", try_force=True)
