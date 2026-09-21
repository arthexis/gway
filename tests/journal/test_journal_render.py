import pytest

from gway import Gateway
from gway.journal import MutationState, UncommittedJournalError
from gway.snapshot import restore_path


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    return Gateway()


def test_render_with_rollback_records_applied_snapshot_for_existing_file(
    gateway,
    tmp_path,
):
    template = tmp_path / "template.conf"
    template.write_text("new [value]\n", encoding="utf-8")
    destination = tmp_path / "target.conf"
    destination.write_text("old\n", encoding="utf-8")
    gateway.context["value"] = "content"

    result = gateway.render(
        str(template),
        to=str(destination),
        rollback="deploy",
    )

    assert result == destination
    assert destination.read_text(encoding="utf-8") == "new content\n"

    journal = gateway.journal.require_open("deploy")
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.state is MutationState.APPLIED
    assert entry.data["operation"] == "render"
    assert len(entry.data["paths"]) == 1
    snapshot = entry.data["paths"][0]
    assert snapshot["path"] == str(destination)
    assert snapshot["existed"] is True

    restore_path(
        snapshot,
        gateway.journal.entry_storage("deploy", entry.sequence) / snapshot["storage"],
    )
    assert destination.read_text(encoding="utf-8") == "old\n"


def test_render_with_rollback_records_absent_destination(gateway, tmp_path):
    template = tmp_path / "template.conf"
    template.write_text("created\n", encoding="utf-8")
    destination = tmp_path / "new.conf"

    gateway.render(
        str(template),
        to=str(destination),
        rollback="deploy",
    )

    entry = gateway.journal.require_open("deploy").entries[0]
    snapshot = entry.data["paths"][0]
    assert entry.state is MutationState.APPLIED
    assert snapshot == {
        "path": str(destination),
        "existed": False,
        "storage": "paths/000000",
    }

    restore_path(
        snapshot,
        gateway.journal.entry_storage("deploy", entry.sequence),
    )
    assert not destination.exists()


def test_render_without_rollback_creates_no_journal(gateway, tmp_path):
    template = tmp_path / "template.conf"
    template.write_text("plain\n", encoding="utf-8")
    destination = tmp_path / "target.conf"

    gateway.render(str(template), to=str(destination))

    assert destination.read_text(encoding="utf-8") == "plain\n"
    assert gateway.journal.open_names() == ()


def test_render_failure_before_snapshot_creates_no_journal(gateway, tmp_path):
    missing = tmp_path / "missing-template.conf"

    with pytest.raises(FileNotFoundError):
        gateway.render(
            str(missing),
            to=str(tmp_path / "target.conf"),
            rollback="deploy",
        )

    assert gateway.journal.open_names() == ()


def test_render_write_failure_leaves_entry_unsealed(
    gateway,
    tmp_path,
    monkeypatch,
):
    template = tmp_path / "template.conf"
    template.write_text("new\n", encoding="utf-8")
    destination = tmp_path / "target.conf"
    destination.write_text("old\n", encoding="utf-8")

    def fail_write(destination, content, *, identity=None):
        raise OSError("simulated write failure")

    monkeypatch.setattr("gway.rendering.atomic_write_text", fail_write)

    with pytest.raises(OSError, match="simulated write failure"):
        gateway.render(
            str(template),
            to=str(destination),
            rollback="deploy",
        )

    journal = gateway.journal.require_open("deploy")
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert entry.state is MutationState.MUTATED
    assert destination.read_text(encoding="utf-8") == "old\n"


def test_render_public_dispatch_accepts_rollback_flag(gateway, tmp_path):
    template = tmp_path / "template.conf"
    template.write_text("public\n", encoding="utf-8")
    destination = tmp_path / "target.conf"

    with pytest.raises(UncommittedJournalError):
        gateway(
            [
                "render",
                str(template),
                "--to",
                str(destination),
                "--rollback",
                "deploy",
            ]
        )

    assert not destination.exists()
    assert gateway.journal.get("deploy") is None


def test_update_entry_data_requires_prepared_entry(tmp_path):
    from gway.journal import JournalError, JournalManager

    journals = JournalManager(tmp_path / "rollback", session_id="session")
    entry = journals.prepare("deploy")
    journals.mark_applied("deploy", entry.sequence)

    with pytest.raises(JournalError, match="not prepared"):
        journals.update_entry_data(
            "deploy",
            entry.sequence,
            {"operation": "render"},
        )
