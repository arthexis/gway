import logging

import pytest

from gway.journal import JournalError


def test_public_commit_closes_transaction(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

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

    result = gateway(["commit", "deploy"])

    assert result == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None


def test_public_rollback_restores_transaction(gateway, tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("before", encoding="utf-8")

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

    result = gateway(["rollback", "deploy"])

    assert result == "deploy"
    assert destination.read_text(encoding="utf-8") == "before"
    assert gateway.journal.get("deploy") is None


def test_public_commit_missing_journal_is_error(gateway):
    with pytest.raises(JournalError, match="not open"):
        gateway(["commit", "missing"])


def test_public_rollback_missing_journal_is_error(gateway):
    with pytest.raises(JournalError, match="not open"):
        gateway(["rollback", "missing"])


def test_public_commit_rejects_journal_without_applied_mutations(gateway):
    gateway.journal.prepare("deploy")

    with pytest.raises(JournalError, match="no applied mutations"):
        gateway(["commit", "deploy"])


def test_transaction_lifecycle_logs_at_info(gateway, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    gateway(["commit", "deploy"])

    messages = [record.getMessage() for record in caplog.records]
    assert "opened rollback journal 'deploy'" in messages
    assert "committed rollback journal 'deploy'" in messages


def test_public_rollback_logs_lifecycle_at_info(gateway, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.copy(str(source), to=str(destination), rollback="deploy")
    gateway(["rollback", "deploy"])

    messages = [record.getMessage() for record in caplog.records]
    assert "rolling back journal 'deploy'" in messages
    assert "rolled back journal 'deploy'" in messages


@pytest.mark.parametrize("operation", ["copy", "move", "link"])
def test_transfer_without_rollback_logs_debug(
    gateway,
    tmp_path,
    caplog,
    operation,
):
    caplog.set_level(logging.DEBUG, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / f"{operation}.txt"

    getattr(gateway, operation)(str(source), to=str(destination))

    messages = [record.getMessage() for record in caplog.records]
    assert (
        f"rollback-capable {operation} executed without journal"
        in messages
    )


def test_remove_without_rollback_logs_debug(gateway, tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="gway")
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")

    gateway.remove(str(target))

    messages = [record.getMessage() for record in caplog.records]
    assert "rollback-capable remove executed without journal" in messages


def test_render_without_rollback_logs_debug(gateway, tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="gway")
    template = tmp_path / "template.txt"
    template.write_text("rendered", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.render(str(template), to=str(destination))

    messages = [record.getMessage() for record in caplog.records]
    assert "rollback-capable render executed without journal" in messages


def test_journaled_move_logs_transaction_debug(gateway, tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="gway")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    gateway.move(str(source), to=str(destination), rollback="deploy")

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        message.startswith("transaction mutation journal=deploy operation=move")
        for message in messages
    )
    assert any(
        message.startswith("transaction snapshot capture path=")
        for message in messages
    )
