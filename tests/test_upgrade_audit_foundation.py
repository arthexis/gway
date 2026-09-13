from pathlib import Path
from types import SimpleNamespace

from gway.config import GwayConfig, GwayPaths
from gway.project import Project
from gway.repository import RepositoryManager, WorkingTreeEntry
from gway.upgrade import UpgradeResult


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
            "-z",
        ]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
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
