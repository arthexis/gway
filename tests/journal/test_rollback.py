import pytest

from gway.journal import JournalError, MutationState, RollbackError
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
    assert (
        gateway.journal.require_open("deploy").entries[0].state
        is MutationState.ROLLED_BACK
    )


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

    with pytest.raises(RollbackError) as raised:
        gateway.journal.rollback("deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.ROLLED_BACK,
        MutationState.APPLIED,
    ]
    assert not first.exists()
    assert second.read_text(encoding="utf-8") == "external change"
    assert [failure.sequence for failure in raised.value.failures] == [2]
    assert isinstance(raised.value.failures[0].error, DriftError)


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

    with pytest.raises(RollbackError) as raised:
        gateway.journal.rollback("deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.APPLIED,
        MutationState.ROLLED_BACK,
    ]
    assert first.read_text(encoding="utf-8") == "external change"
    assert not second.exists()
    assert [failure.sequence for failure in raised.value.failures] == [1]
    assert isinstance(raised.value.failures[0].error, DriftError)


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


def test_rollback_entry_uses_persisted_execution_identity(
    gateway,
    tmp_path,
    host_calls,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(
        str(source),
        to=str(destination),
        sudo=True,
        rollback="deploy",
    )
    entry = gateway.journal.require_open("deploy").entries[0]

    gateway.journal.rollback_entry("deploy", entry.sequence)

    assert entry.state is MutationState.ROLLED_BACK
    assert entry.data["identity"] == {"user": "root"}
    assert host_calls[-1] == (
        ("sudo", "rm", "-rf", "--", str(destination)),
        {"check": True},
    )


def test_rollback_entry_rejects_incomplete_expected_fingerprints_before_restore(
    gateway,
    tmp_path,
    monkeypatch,
):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    entry = gateway.journal.prepare(
        "deploy",
        kind="filesystem",
        data={
            "operation": "move",
            "identity": {"user": None},
            "paths": [
                {
                    "path": str(first),
                    "existed": False,
                    "storage": "paths/000000",
                },
                {
                    "path": str(second),
                    "existed": False,
                    "storage": "paths/000001",
                },
            ],
        },
    )
    gateway.journal.mark_applied("deploy", entry.sequence)
    entry.data["expected"] = entry.data["expected"][:1]
    gateway.journal._persist(gateway.journal.require_open("deploy"))

    restored = []

    def record_restore(*args, **kwargs):
        restored.append((args, kwargs))

    monkeypatch.setattr("gway.snapshot.restore_path", record_restore)

    with pytest.raises(JournalError, match="incomplete post-mutation fingerprints"):
        gateway.journal.rollback_entry("deploy", entry.sequence)

    assert restored == []
    assert entry.state is MutationState.APPLIED


def test_rollback_entry_calls_restore_in_reverse_snapshot_order(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = gateway.journal.require_open("deploy").entries[0]
    restored = []

    def record_restore(snapshot, storage, *, identity=None, expected=None):
        restored.append(str(snapshot["path"]))
        return snapshot["path"]

    monkeypatch.setattr("gway.snapshot.restore_path", record_restore)

    gateway.journal.rollback_entry("deploy", entry.sequence)

    assert restored == [str(destination), str(source)]
    assert entry.state is MutationState.ROLLED_BACK


def test_whole_journal_collects_multiple_entry_failures_in_lifo_order(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    third = tmp_path / "third.txt"

    gateway.copy(str(source), to=str(first), rollback="deploy")
    gateway.copy(str(source), to=str(second), rollback="deploy")
    gateway.copy(str(source), to=str(third), rollback="deploy")

    first.write_text("external first", encoding="utf-8")
    third.write_text("external third", encoding="utf-8")

    with pytest.raises(RollbackError) as raised:
        gateway.journal.rollback("deploy")

    error = raised.value
    assert error.attempted == 3
    assert [failure.sequence for failure in error.failures] == [3, 1]
    assert [failure.operation for failure in error.failures] == ["copy", "copy"]
    assert all(isinstance(failure.error, DriftError) for failure in error.failures)

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.APPLIED,
        MutationState.ROLLED_BACK,
        MutationState.APPLIED,
    ]
    assert first.read_text(encoding="utf-8") == "external first"
    assert not second.exists()
    assert third.read_text(encoding="utf-8") == "external third"


def test_incomplete_rollback_preserves_snapshot_material_for_retry(
    gateway,
    tmp_path,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    gateway.copy(str(source), to=str(first), rollback="deploy")
    gateway.copy(str(source), to=str(second), rollback="deploy")

    journal_dir = gateway.journal._directory("deploy")
    second_storage = gateway.journal.entry_storage("deploy", 2)
    second.write_text("external change", encoding="utf-8")

    with pytest.raises(RollbackError):
        gateway.journal.rollback("deploy")

    assert journal_dir.exists()
    assert second_storage.exists()
    assert (
        gateway.journal.require_open("deploy").entries[1].state is MutationState.APPLIED
    )


def test_retry_only_attempts_unresolved_entries_and_closes_when_complete(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"

    gateway.copy(str(source), to=str(first), rollback="deploy")
    gateway.copy(str(source), to=str(second), rollback="deploy")

    second.write_text("external change", encoding="utf-8")

    with pytest.raises(RollbackError):
        gateway.journal.rollback("deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.state for entry in journal.entries] == [
        MutationState.ROLLED_BACK,
        MutationState.APPLIED,
    ]

    original = gateway.journal.rollback_entry
    attempted = []

    def record_attempt(name, sequence):
        attempted.append(sequence)
        return original(name, sequence)

    monkeypatch.setattr(gateway.journal, "rollback_entry", record_attempt)

    second.write_text("source", encoding="utf-8")
    gateway.journal.rollback("deploy")

    assert attempted == [2]
    assert gateway.journal.get("deploy") is None
    assert not first.exists()
    assert not second.exists()


def test_retry_error_attempt_count_only_includes_unresolved_entries(
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

    with pytest.raises(RollbackError):
        gateway.journal.rollback("deploy")

    with pytest.raises(RollbackError) as retry:
        gateway.journal.rollback("deploy")

    assert retry.value.attempted == 1
    assert [failure.sequence for failure in retry.value.failures] == [2]
