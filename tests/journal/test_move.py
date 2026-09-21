import pytest

from gway.journal import MutationState
from gway.snapshot import DriftError, restore_path


def _move_entry(gateway, name="deploy"):
    return gateway.journal.require_open(name).entries[-1]


def _snapshot_storage(gateway, entry, snapshot, name="deploy"):
    return gateway.journal.entry_storage(name, entry.sequence) / snapshot["storage"]


def _restore_move(gateway, entry, name="deploy"):
    source_snapshot, destination_snapshot = entry.data["paths"]
    source_expected, destination_expected = entry.data["expected"]

    restore_path(
        destination_snapshot,
        _snapshot_storage(gateway, entry, destination_snapshot, name),
        expected=destination_expected,
    )
    restore_path(
        source_snapshot,
        _snapshot_storage(gateway, entry, source_snapshot, name),
        expected=source_expected,
    )


def test_move_records_one_logical_entry_with_two_paths(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    result = gateway.move(str(source), to=str(destination), rollback="deploy")

    assert result == destination
    entry = _move_entry(gateway)
    assert entry.state is MutationState.APPLIED
    assert entry.data["operation"] == "move"
    assert len(entry.data["paths"]) == 2
    assert [snapshot["path"] for snapshot in entry.data["paths"]] == [
        str(source),
        str(destination),
    ]
    assert [snapshot["storage"] for snapshot in entry.data["paths"]] == [
        "paths/000000",
        "paths/000001",
    ]


def test_move_to_absent_destination_can_restore_both_sides(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = _move_entry(gateway)

    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "source"

    _restore_move(gateway, entry)

    assert source.read_text(encoding="utf-8") == "source"
    assert not destination.exists()


def test_move_over_existing_file_can_restore_both_sides(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("destination", encoding="utf-8")

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = _move_entry(gateway)

    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "source"

    _restore_move(gateway, entry)

    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "destination"


def test_move_into_directory_snapshots_resolved_target(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    target = destination / source.name

    result = gateway.move(str(source), to=str(destination), rollback="deploy")

    assert result == target
    entry = _move_entry(gateway)
    assert [snapshot["path"] for snapshot in entry.data["paths"]] == [
        str(source),
        str(target),
    ]

    _restore_move(gateway, entry)

    assert source.read_text(encoding="utf-8") == "source"
    assert destination.is_dir()
    assert not target.exists()


def test_move_directory_can_restore_tree(gateway, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested.txt").write_text("nested", encoding="utf-8")
    destination = tmp_path / "destination"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = _move_entry(gateway)

    assert not source.exists()
    assert (destination / "nested.txt").read_text(encoding="utf-8") == "nested"

    _restore_move(gateway, entry)

    assert (source / "nested.txt").read_text(encoding="utf-8") == "nested"
    assert not destination.exists()


def test_move_failure_after_snapshots_leaves_one_unsealed_entry(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("destination", encoding="utf-8")

    def fail_move(source, destination):
        raise OSError("move failed")

    monkeypatch.setattr("gway.filesystem._move_local", fail_move)

    with pytest.raises(OSError, match="move failed"):
        gateway.move(str(source), to=str(destination), rollback="deploy")

    journal = gateway.journal.require_open("deploy")
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.state is MutationState.MUTATED
    assert len(entry.data["paths"]) == 2
    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "destination"


def test_move_without_rollback_creates_no_journal(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination))

    assert gateway.journal.open_names() == ()


def test_move_detects_destination_drift(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = _move_entry(gateway)
    destination.write_text("changed elsewhere", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)

    assert destination.read_text(encoding="utf-8") == "changed elsewhere"


def test_move_detects_source_recreation_drift(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")
    entry = _move_entry(gateway)
    source.write_text("new external source", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)

    assert source.read_text(encoding="utf-8") == "new external source"


def test_move_counts_as_one_sequence_between_other_mutations(gateway, tmp_path):
    original = tmp_path / "original.txt"
    original.write_text("original", encoding="utf-8")
    copied = tmp_path / "copied.txt"
    moved = tmp_path / "moved.txt"
    removed = tmp_path / "removed.txt"
    removed.write_text("removed", encoding="utf-8")

    gateway.copy(str(original), to=str(copied), rollback="deploy")
    gateway.move(str(copied), to=str(moved), rollback="deploy")
    gateway.remove(str(removed), rollback="deploy")

    journal = gateway.journal.require_open("deploy")
    assert [entry.sequence for entry in journal.entries] == [1, 2, 3]
    assert [entry.data["operation"] for entry in journal.entries] == [
        "copy",
        "move",
        "remove",
    ]
    assert len(journal.entries[1].data["paths"]) == 2
