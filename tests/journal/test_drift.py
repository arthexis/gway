import os

import pytest

from gway.journal import MutationState
from gway.snapshot import DriftError, restore_path


def _entry(gateway, name="deploy"):
    return gateway.journal.require_open(name).entries[-1]


def _guarded_restore(gateway, entry, name="deploy"):
    snapshot = entry.data["paths"][0]
    expected = entry.data["expected"][0]
    return restore_path(
        snapshot,
        gateway.journal.entry_storage(name, entry.sequence),
        expected=expected,
    )


def test_applied_file_entry_records_expected_post_state(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    gateway.copy(str(source), to=str(destination), rollback="deploy")

    entry = _entry(gateway)
    expected = entry.data["expected"][0]
    assert entry.state is MutationState.APPLIED
    assert expected["path"] == str(destination)
    assert expected["type"] == "file"
    assert len(expected["sha256"]) == 64


def test_guarded_restore_succeeds_when_applied_file_is_unchanged(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)

    _guarded_restore(gateway, entry)

    assert destination.read_text(encoding="utf-8") == "old"


def test_guarded_restore_refuses_external_file_content_change(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"
    destination.write_text("old", encoding="utf-8")

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)
    destination.write_text("changed elsewhere", encoding="utf-8")

    with pytest.raises(DriftError, match="changed after GWay applied"):
        _guarded_restore(gateway, entry)

    assert destination.read_text(encoding="utf-8") == "changed elsewhere"
    assert entry.state is MutationState.APPLIED


def test_verify_applied_refuses_metadata_drift(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)
    destination.chmod(0o600)

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)


def test_verify_applied_accepts_unchanged_removed_path(gateway, tmp_path):
    target = tmp_path / "remove.txt"
    target.write_text("old", encoding="utf-8")

    gateway.remove(str(target), rollback="deploy")
    entry = _entry(gateway)

    gateway.journal.verify_applied("deploy", entry.sequence)

    assert entry.data["expected"][0] == {
        "path": str(target),
        "existed": False,
    }


def test_verify_applied_detects_recreated_removed_path(gateway, tmp_path):
    target = tmp_path / "remove.txt"
    target.write_text("old", encoding="utf-8")

    gateway.remove(str(target), rollback="deploy")
    entry = _entry(gateway)
    target.write_text("new process", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)


def test_verify_applied_detects_symlink_retargeting(gateway, tmp_path):
    original = tmp_path / "original.txt"
    other = tmp_path / "other.txt"
    original.write_text("original", encoding="utf-8")
    other.write_text("other", encoding="utf-8")
    link = tmp_path / "current"

    gateway.link(str(original), to=str(link), rollback="deploy")
    entry = _entry(gateway)

    link.unlink()
    link.symlink_to(other)

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)


def test_verify_applied_detects_directory_tree_content_drift(gateway, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("new", encoding="utf-8")
    destination = tmp_path / "target"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)
    (destination / "value.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)


def test_verify_applied_detects_directory_tree_membership_drift(gateway, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("new", encoding="utf-8")
    destination = tmp_path / "target"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)
    (destination / "extra.txt").write_text("external", encoding="utf-8")

    with pytest.raises(DriftError):
        gateway.journal.verify_applied("deploy", entry.sequence)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_expected_fingerprint_survives_manifest_reload(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "target.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    entry = _entry(gateway)

    gateway.journal._journals.clear()
    reloaded = gateway.journal.require_open("deploy").entries[0]

    assert reloaded.data["expected"] == entry.data["expected"]
    gateway.journal.verify_applied("deploy", reloaded.sequence)
