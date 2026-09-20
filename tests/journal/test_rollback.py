import pytest

from gway.journal import JournalError, MutationState
from gway.snapshot import DriftError


def test_rollback_entry_restores_single_path_and_marks_entry(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = gateway.journal.require_open("deploy").entries[0]

    restored = gateway.journal.rollback_entry("deploy", entry.sequence)

    assert restored.state is MutationState.ROLLED_BACK
    assert destination.read_text(encoding="utf-8") == "old"
    assert gateway.journal.require_open("deploy").entries[0].state is MutationState.ROLLED_BACK


def test_rollback_entry_verifies_all_move_paths_before_restoring_any(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = gateway.journal.require_open("deploy").entries[0]

    source.write_text("external recreation", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.rollback_entry("deploy", entry.sequence)

    assert source.read_text(encoding="utf-8") == "external recreation"
    assert destination.read_text(encoding="utf-8") == "source"
    assert entry.state is MutationState.APPLIED


def test_rollback_entry_restores_move_paths_in_reverse_path_order(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("destination", encoding="utf-8")

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = gateway.journal.require_open("deploy").entries[0]

    gateway.journal.rollback_entry("deploy", entry.sequence)

    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "destination"
    assert entry.state is MutationState.ROLLED_BACK


def test_whole_journal_rolls_back_applied_entries_lifo(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    copied = tmp_path / "copied.txt"
    moved = tmp_path / "moved.txt"
    removed = tmp_path / "removed.txt"
    removed.write_text("removed", encoding="utf-8")

    gateway.copy(str(source), to=str(copied), rollback="deploy")
    gateway.move(str(copied), to=str(moved), rollback="deploy")
    gateway.remove(str(removed), rollback="deploy")

    gateway.journal.rollback("deploy")

    assert source.read_text(encoding="utf-8") == "source"
    assert not copied.exists()
    assert not moved.exists()
    assert removed.read_text(encoding="utf-8") == "removed"
    assert gateway.journal.get("deploy") is None
    assert gateway.journal.open_names() == ()


def test_whole_journal_skips_prepared_entries(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    prepared = gateway.journal.prepare(
        "deploy",
        kind="filesystem",
        data={"operation": "future"},
    )

    gateway.journal.rollback("deploy")

    assert not destination.exists()
    assert prepared.state is MutationState.PREPARED
    assert gateway.journal.get("deploy") is None


def test_whole_journal_failure_preserves_open_journal_and_applied_entry(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    gateway.copy(str(source), to=str(first), rollback="deploy")
    gateway.copy(str(source), to=str(second), rollback="deploy")

    second.write_text("external change", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.rollback("deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.APPLIED,
        MutationState.APPLIED,
    ]
    assert first.exists()
    assert second.read_text(encoding="utf-8") == "external change"


def test_whole_journal_failure_after_later_entry_restored_preserves_progress(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    gateway.copy(str(source), to=str(first), rollback="deploy")
    gateway.copy(str(source), to=str(second), rollback="deploy")

    first.write_text("external change", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.rollback("deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.APPLIED,
        MutationState.ROLLED_BACK,
    ]
    assert first.read_text(encoding="utf-8") == "external change"
    assert not second.exists()


def test_rollback_entry_rejects_non_applied_entry(gateway):
    entry = gateway.journal.prepare("deploy")

    with pytest.raises(JournalError, match="not applied"):
        gateway.journal.rollback_entry("deploy", entry.sequence)


def test_rollback_entry_rejects_unsupported_kind(gateway):
    entry = gateway.journal.prepare(
        "deploy",
        kind="service",
        data={"operation": "restart"},
    )
    gateway.journal.mark_applied("deploy", entry.sequence)

    with pytest.raises(JournalError, match="unsupported kind"):
        gateway.journal.rollback_entry("deploy", entry.sequence)


def test_rollback_entry_requires_snapshot_storage_metadata(gateway, tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    entry = gateway.journal.prepare(
        "deploy",
        kind="filesystem",
        data={
            "operation": "copy",
            "identity": {"user": None},
            "paths": [{"path": str(target), "existed": False}],
        },
    )
    gateway.journal.mark_applied("deploy", entry.sequence)

    with pytest.raises(JournalError, match="no storage location"):
        gateway.journal.rollback_entry("deploy", entry.sequence)
