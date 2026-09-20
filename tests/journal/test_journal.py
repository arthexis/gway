import json

import pytest

from gway.journal import (
    JournalError,
    JournalManager,
    JournalState,
    MutationState,
)


def manager(tmp_path, *, session_id="session"):
    return JournalManager(tmp_path / "rollback", session_id=session_id)


def test_prepare_opens_named_journal_and_persists_manifest(tmp_path):
    journals = manager(tmp_path)

    entry = journals.prepare(
        "deploy",
        kind="filesystem",
        data={"operation": "render", "path": "/etc/example.conf"},
    )

    journal = journals.get("deploy")
    assert journal is not None
    assert journal.state is JournalState.OPEN
    assert entry.sequence == 1
    assert entry.state is MutationState.PREPARED
    assert journal.entries == [entry]

    manifest = tmp_path / "rollback" / "session" / "deploy" / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["name"] == "deploy"
    assert payload["state"] == "open"
    assert payload["entries"][0]["state"] == "prepared"
    assert payload["entries"][0]["data"]["operation"] == "render"


def test_manager_reloads_open_journal_from_persisted_manifest(tmp_path):
    first = manager(tmp_path)
    first.prepare("deploy", data={"path": "/one"})
    first.mark_applied("deploy", 1)

    second = manager(tmp_path)

    journal = second.get("deploy")
    assert journal is not None
    assert journal.name == "deploy"
    assert journal.state is JournalState.OPEN
    assert len(journal.entries) == 1
    assert journal.entries[0].state is MutationState.APPLIED
    assert journal.entries[0].data == {"path": "/one"}
    assert second.open_names() == ("deploy",)


def test_prepare_appends_monotonic_entries(tmp_path):
    journals = manager(tmp_path)

    first = journals.prepare("deploy")
    second = journals.prepare("deploy")
    third = journals.prepare("deploy")

    assert [first.sequence, second.sequence, third.sequence] == [1, 2, 3]


def test_mark_applied_requires_prepared_entry(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")

    applied = journals.mark_applied("deploy", 1)

    assert applied.state is MutationState.APPLIED
    with pytest.raises(JournalError, match="not prepared"):
        journals.mark_applied("deploy", 1)


def test_mark_rolled_back_requires_applied_entry(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")

    with pytest.raises(JournalError, match="not applied"):
        journals.mark_rolled_back("deploy", 1)

    journals.mark_applied("deploy", 1)
    restored = journals.mark_rolled_back("deploy", 1)
    assert restored.state is MutationState.ROLLED_BACK


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        "../escape",
        "nested/name",
        r"nested\\name",
        ".leading",
    ],
)
def test_invalid_journal_names_are_rejected(tmp_path, name):
    journals = manager(tmp_path)

    with pytest.raises(ValueError, match="Invalid rollback journal name"):
        journals.prepare(name)


def test_require_open_rejects_missing_journal(tmp_path):
    journals = manager(tmp_path)

    with pytest.raises(JournalError, match="not open"):
        journals.require_open("missing")


def test_unknown_entry_sequence_is_an_error(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")

    with pytest.raises(JournalError, match="has no entry 2"):
        journals.mark_applied("deploy", 2)

    with pytest.raises(JournalError, match="has no entry 0"):
        journals.mark_applied("deploy", 0)


def test_commit_requires_at_least_one_applied_mutation(tmp_path):
    journals = manager(tmp_path)

    with pytest.raises(JournalError, match="not open"):
        journals.commit("missing")

    journals.prepare("deploy")
    with pytest.raises(JournalError, match="no applied mutations"):
        journals.commit("deploy")


def test_commit_discards_persisted_journal(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")
    journals.mark_applied("deploy", 1)

    journals.commit("deploy")

    assert journals.get("deploy") is None
    assert journals.open_names() == ()
    assert not (tmp_path / "rollback" / "session" / "deploy").exists()


def test_close_rolled_back_requires_no_applied_mutations(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")
    journals.mark_applied("deploy", 1)

    with pytest.raises(JournalError, match="still has applied mutations"):
        journals.close_rolled_back("deploy")

    journals.mark_rolled_back("deploy", 1)
    journals.close_rolled_back("deploy")

    assert journals.get("deploy") is None
    assert journals.open_names() == ()


def test_prepared_but_unapplied_entry_does_not_block_rolled_back_close(tmp_path):
    journals = manager(tmp_path)
    journals.prepare("deploy")

    journals.close_rolled_back("deploy")

    assert journals.get("deploy") is None


def test_sessions_are_isolated_under_same_storage_root(tmp_path):
    first = JournalManager(tmp_path / "rollback", session_id="first")
    second = JournalManager(tmp_path / "rollback", session_id="second")

    first.prepare("deploy")
    second.prepare("deploy")

    assert first.open_names() == ("deploy",)
    assert second.open_names() == ("deploy",)
    assert first._manifest("deploy") != second._manifest("deploy")
