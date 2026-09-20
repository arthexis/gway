import os

import pytest

from gway.journal import (
    JournalError,
    MutationState,
    RollbackError,
    UncommittedJournalError,
    rollback_error_for,
)
from gway.snapshot import restore_path


def _entry(gateway, name="deploy", index=0):
    return gateway.journal.require_open(name).entries[index]


def _restore(gateway, entry, name="deploy"):
    snapshot = entry.data["paths"][0]
    restore_path(
        snapshot,
        gateway.journal.entry_storage(name, entry.sequence) / snapshot["storage"],
    )


def test_copy_with_rollback_restores_existing_destination(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    with pytest.raises(UncommittedJournalError):
        gateway(
            [
                "copy",
                str(source),
                "--to",
                str(destination),
                "--rollback",
                "deploy",
            ]
        )

    assert destination.read_text(encoding="utf-8") == "old"
    assert gateway.journal.get("deploy") is None


def test_copy_with_rollback_removes_new_destination_on_restore(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")

    entry = _entry(gateway)
    assert entry.data["paths"][0] == {
        "path": str(destination),
        "existed": False,
        "storage": "paths/000000",
    }

    _restore(gateway, entry)
    assert not destination.exists()


def test_copy_without_rollback_creates_no_journal(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"

    gateway.copy(str(source), to=str(destination))

    assert gateway.journal.open_names() == ()


def test_copy_failure_after_snapshot_leaves_prepared_entry(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    def fail_copy(source, destination):
        raise OSError("copy failed")

    monkeypatch.setattr("gway.filesystem._copy_local", fail_copy)

    with pytest.raises(OSError, match="copy failed"):
        gateway.copy(str(source), to=str(destination), rollback="deploy")

    entry = _entry(gateway)
    assert entry.state is MutationState.PREPARED
    assert destination.read_text(encoding="utf-8") == "old"


def test_link_conflict_is_rejected_before_journal_entry(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "current"
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        gateway.link(str(source), to=str(destination), rollback="deploy")

    assert destination.read_text(encoding="utf-8") == "existing"
    assert gateway.journal.open_names() == ()


def test_link_with_rollback_removes_new_link_on_restore(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "linked.txt"

    gateway.link(str(source), to=str(destination), rollback="deploy")

    entry = _entry(gateway)
    assert destination.is_symlink()
    _restore(gateway, entry)
    assert not destination.exists()
    assert not destination.is_symlink()


def test_idempotent_link_does_not_create_rollback_entry(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "linked.txt"
    destination.symlink_to(source)

    result = gateway.link(str(source), to=str(destination), rollback="deploy")

    assert result == destination
    assert gateway.journal.open_names() == ()


def test_link_failure_after_snapshot_leaves_prepared_entry(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "linked.txt"

    def fail_link(source, destination):
        raise OSError("link failed")

    monkeypatch.setattr("gway.filesystem._link_local", fail_link)

    with pytest.raises(OSError, match="link failed"):
        gateway.link(str(source), to=str(destination), rollback="deploy")

    assert _entry(gateway).state is MutationState.PREPARED


def test_remove_with_rollback_restores_file(gateway, tmp_path):
    target = tmp_path / "remove.txt"
    target.write_text("keep", encoding="utf-8")

    gateway.remove(str(target), rollback="deploy")

    assert not target.exists()
    entry = _entry(gateway)
    assert entry.state is MutationState.APPLIED
    assert entry.data["operation"] == "remove"

    _restore(gateway, entry)
    assert target.read_text(encoding="utf-8") == "keep"


def test_remove_with_rollback_restores_symlink(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("keep", encoding="utf-8")
    target = tmp_path / "link.txt"
    target.symlink_to(source)

    gateway.remove(str(target), rollback="deploy")

    entry = _entry(gateway)
    _restore(gateway, entry)

    assert target.is_symlink()
    assert os.readlink(target) == str(source)


def test_remove_with_rollback_restores_empty_directory(gateway, tmp_path):
    target = tmp_path / "empty"
    target.mkdir()

    gateway.remove(str(target), rollback="deploy")

    entry = _entry(gateway)
    _restore(gateway, entry)

    assert target.is_dir()


def test_remove_failure_after_snapshot_leaves_prepared_entry(
    gateway,
    tmp_path,
    monkeypatch,
):
    target = tmp_path / "remove.txt"
    target.write_text("keep", encoding="utf-8")

    def fail_remove(path):
        raise OSError("remove failed")

    monkeypatch.setattr("gway.filesystem._remove_local", fail_remove)

    with pytest.raises(OSError, match="remove failed"):
        gateway.remove(str(target), rollback="deploy")

    assert _entry(gateway).state is MutationState.PREPARED
    assert target.read_text(encoding="utf-8") == "keep"


def test_multiple_filesystem_mutations_share_monotonic_journal_sequence(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    copied = tmp_path / "copied.txt"
    linked = tmp_path / "linked.txt"
    removed = tmp_path / "removed.txt"
    removed.write_text("removed", encoding="utf-8")

    gateway.copy(str(source), to=str(copied), rollback="deploy")
    gateway.link(str(source), to=str(linked), rollback="deploy")
    gateway.remove(str(removed), rollback="deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.sequence for entry in journal.entries] == [1, 2, 3]
    assert [entry.data["operation"] for entry in journal.entries] == [
        "copy",
        "link",
        "remove",
    ]
    assert all(entry.state is MutationState.APPLIED for entry in journal.entries)


def test_post_mutation_fingerprint_failure_retains_unsealed_journal(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    primary = OSError("fingerprint failed")

    def fail_fingerprint(*args, **kwargs):
        raise primary

    monkeypatch.setattr("gway.snapshot.fingerprint_path", fail_fingerprint)

    with pytest.raises(OSError) as raised:
        gateway(
            [
                "copy",
                str(source),
                "--to",
                str(destination),
                "--rollback",
                "deploy",
            ]
        )

    assert raised.value is primary
    assert destination.read_text(encoding="utf-8") == "new"

    journal = gateway.journal.require_open("deploy")
    entry = journal.entries[0]
    assert entry.state is MutationState.MUTATED

    recovery = rollback_error_for(primary)
    assert isinstance(recovery, RollbackError)
    assert recovery.journal == "deploy"
    assert recovery.failures[0].sequence == 1
    assert "post-mutation fingerprint is unavailable" in str(
        recovery.failures[0].error
    )

    with pytest.raises(JournalError, match="unsealed mutations"):
        gateway.journal.commit("deploy")
