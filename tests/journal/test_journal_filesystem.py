import os
from pathlib import Path
import stat

import pytest

from gway.journal import JournalManager
from gway.snapshot import SnapshotError, capture_path, restore_path


def _set_times(path: Path, *, atime_ns: int, mtime_ns: int, follow_symlinks=True):
    os.utime(
        path,
        ns=(atime_ns, mtime_ns),
        follow_symlinks=follow_symlinks,
    )


def test_capture_and_restore_existing_file_preserves_contents_mode_and_timestamps(
    tmp_path,
):
    path = tmp_path / "config"
    path.write_bytes(b"before\n")
    path.chmod(0o640)
    atime_ns = 1_600_000_000_123_456_789
    mtime_ns = 1_600_000_100_987_654_321
    _set_times(path, atime_ns=atime_ns, mtime_ns=mtime_ns)

    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(path, storage)

    path.write_bytes(b"after\n")
    path.chmod(0o600)
    _set_times(path, atime_ns=atime_ns + 10_000, mtime_ns=mtime_ns + 10_000)

    restore_path(snapshot, storage)

    info = path.stat()
    assert path.read_bytes() == b"before\n"
    assert stat.S_IMODE(info.st_mode) == 0o640
    assert info.st_mtime_ns == mtime_ns
    assert info.st_atime_ns == atime_ns
    assert snapshot["uid"] == info.st_uid
    assert snapshot["gid"] == info.st_gid


def test_capture_missing_path_restores_absence(tmp_path):
    path = tmp_path / "created-later"
    storage = tmp_path / "journal" / "entry"

    snapshot = capture_path(path, storage)
    assert snapshot == {"path": str(path), "existed": False}

    path.write_text("transaction output", encoding="utf-8")
    restore_path(snapshot, storage)

    assert not path.exists()


def test_restore_missing_path_removes_transaction_created_directory(tmp_path):
    path = tmp_path / "created-later"
    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(path, storage)

    path.mkdir()
    (path / "nested").write_text("new", encoding="utf-8")

    restore_path(snapshot, storage)

    assert not path.exists()


def test_capture_and_restore_symlink_preserves_link_target(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    link = tmp_path / "current"
    link.symlink_to(first.name)

    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(link, storage)

    link.unlink()
    link.symlink_to(second.name)

    restore_path(snapshot, storage)

    assert link.is_symlink()
    assert os.readlink(link) == first.name
    assert link.read_text(encoding="utf-8") == "one"


def test_capture_and_restore_directory_tree_preserves_root_metadata(tmp_path):
    path = tmp_path / "tree"
    path.mkdir()
    path.chmod(0o750)
    (path / "nested").mkdir()
    (path / "nested" / "file").write_text("before", encoding="utf-8")
    atime_ns = 1_610_000_000_111_222_333
    mtime_ns = 1_610_000_100_444_555_666
    _set_times(path, atime_ns=atime_ns, mtime_ns=mtime_ns)

    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(path, storage)

    (path / "nested" / "file").write_text("after", encoding="utf-8")
    (path / "extra").write_text("extra", encoding="utf-8")
    path.chmod(0o700)

    restore_path(snapshot, storage)

    info = path.stat()
    assert (path / "nested" / "file").read_text(encoding="utf-8") == "before"
    assert not (path / "extra").exists()
    assert stat.S_IMODE(info.st_mode) == 0o750
    assert info.st_mtime_ns == mtime_ns
    assert info.st_atime_ns == atime_ns


def test_file_restore_can_replace_transaction_symlink_atomically(tmp_path):
    original = tmp_path / "config"
    original.write_text("before", encoding="utf-8")
    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(original, storage)

    original.unlink()
    other = tmp_path / "other"
    other.write_text("other", encoding="utf-8")
    original.symlink_to(other.name)

    restore_path(snapshot, storage)

    assert original.is_file()
    assert not original.is_symlink()
    assert original.read_text(encoding="utf-8") == "before"


def test_symlink_restore_can_replace_transaction_file(tmp_path):
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    link = tmp_path / "current"
    link.symlink_to(target.name)
    storage = tmp_path / "journal" / "entry"
    snapshot = capture_path(link, storage)

    link.unlink()
    link.write_text("replacement", encoding="utf-8")

    restore_path(snapshot, storage)

    assert link.is_symlink()
    assert os.readlink(link) == target.name


def test_entry_storage_is_scoped_to_journal_mutation(tmp_path):
    journals = JournalManager(tmp_path / "rollback", session_id="session")
    first = journals.prepare("deploy")
    second = journals.prepare("deploy")

    assert journals.entry_storage("deploy", first.sequence) == (
        tmp_path / "rollback" / "session" / "deploy" / "entries" / "000001"
    )
    assert journals.entry_storage("deploy", second.sequence).name == "000002"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unsupported on this platform")
def test_capture_rejects_unsupported_filesystem_object(tmp_path):
    path = tmp_path / "pipe"
    os.mkfifo(path)

    with pytest.raises(SnapshotError, match="unsupported filesystem object type"):
        capture_path(path, tmp_path / "journal" / "entry")
