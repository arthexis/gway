import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from gway import log as gway_log


@pytest.fixture(autouse=True)
def reset_gway_output_handler():
    original_level = gway_log.logger.level
    original_propagate = gway_log.logger.propagate
    gway_log._remove_output_handler()
    yield
    gway_log._remove_output_handler()
    gway_log.logger.setLevel(original_level)
    gway_log.logger.propagate = original_propagate


def test_default_log_path_uses_durable_data_root(tmp_path):
    assert gway_log.default_log_path(root=tmp_path) == (tmp_path / "logs" / "gway.log")


def test_file_output_rotates_daily_with_thirty_days_total(tmp_path):
    handler = gway_log.configure_output(destination="file", root=tmp_path)

    assert isinstance(handler, TimedRotatingFileHandler)
    assert Path(handler.baseFilename) == tmp_path / "logs" / "gway.log"
    assert handler.when == "MIDNIGHT"
    assert handler.interval == 24 * 60 * 60
    # Twenty-nine archives plus the current file keeps at most 30 days.
    assert handler.backupCount == 29
    assert handler.suffix == "%Y-%m-%d"
    assert handler.level == logging.INFO


def test_file_output_persists_info_without_console_output(tmp_path, capsys):
    gway_log.configure_output(destination="file", root=tmp_path)

    gway_log.info("reconciliation complete")
    for handler in gway_log.logger.handlers:
        handler.flush()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    payload = json.loads(
        (tmp_path / "logs" / "gway.log").read_text(encoding="utf-8")
    )
    assert payload["level"] == "INFO"
    assert payload["source"] == "gway"
    assert payload["message"] == "reconciliation complete"


@pytest.mark.parametrize(
    ("destination", "stream"),
    [("stdout", "out"), ("stderr", "err")],
)
def test_explicit_stream_destination(destination, stream, capsys):
    gway_log.configure_output(destination=destination, level="INFO")

    gway_log.info("visible log")
    captured = capsys.readouterr()

    assert "visible log" in getattr(captured, stream)
    other = "err" if stream == "out" else "out"
    assert getattr(captured, other) == ""


def test_configure_output_replaces_managed_handler_instead_of_duplicating(tmp_path):
    first = gway_log.configure_output(root=tmp_path)
    second = gway_log.configure_output(root=tmp_path)

    managed = [
        handler
        for handler in gway_log.logger.handlers
        if getattr(handler, "_gway_output_handler", False)
    ]
    assert managed == [second]
    assert first not in gway_log.logger.handlers


def test_explicit_file_path_is_supported(tmp_path):
    path = tmp_path / "custom" / "operations.log"

    handler = gway_log.configure_output(destination=path, level="WARNING")
    gway_log.warning("custom destination")
    handler.flush()

    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["message"] == "custom destination"
    assert handler.level == logging.WARNING


def test_default_destination_prefers_journal_when_available(monkeypatch):
    monkeypatch.setattr(gway_log, "_journal_address", lambda: "/run/journal")

    assert gway_log.default_output_destination() == "journal"


def test_default_destination_uses_file_when_journal_unavailable(monkeypatch):
    monkeypatch.setattr(gway_log, "_journal_address", lambda: None)

    assert gway_log.default_output_destination() == "file"


class _FakeJournalSocket:
    def __init__(self):
        self.address = None
        self.payloads = []
        self.closed = False

    def connect(self, address):
        self.address = address

    def send(self, payload):
        self.payloads.append(payload)
        return len(payload)

    def close(self):
        self.closed = True


def test_journal_handler_emits_identifier_and_priority(monkeypatch):
    fake = _FakeJournalSocket()
    monkeypatch.setattr(gway_log, "_journal_address", lambda: "/run/journal")
    monkeypatch.setattr(gway_log._socket, "socket", lambda *args: fake)

    handler = gway_log.configure_output(level="DEBUG")
    gway_log.info("reconciled %s", "service")
    gway_log.warning("retrying")

    assert isinstance(handler, gway_log._JournalHandler)
    assert fake.address == "/run/journal"
    assert fake.payloads == [
        b"<14>gway: reconciled service",
        b"<12>gway: retrying",
    ]


def test_journal_transport_failure_falls_back_to_stderr(monkeypatch, capsys):
    class BrokenSocket(_FakeJournalSocket):
        def connect(self, address):
            raise OSError("journal unavailable")

    monkeypatch.setattr(gway_log, "_journal_address", lambda: "/run/journal")
    monkeypatch.setattr(gway_log._socket, "socket", lambda *args: BrokenSocket())

    gway_log.configure_output(level="INFO")
    gway_log.info("still visible")

    assert "still visible" in capsys.readouterr().err


def test_explicit_journal_destination_falls_back_when_socket_absent(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(gway_log, "_journal_address", lambda: None)

    handler = gway_log.configure_output(destination="journal", level="INFO")
    gway_log.info("fallback")

    assert isinstance(handler, logging.StreamHandler)
    assert "fallback" in capsys.readouterr().err


def test_source_scope_changes_journal_identifier_and_restores(monkeypatch):
    fake = _FakeJournalSocket()
    monkeypatch.setattr(gway_log, "_journal_address", lambda: "/run/journal")
    monkeypatch.setattr(gway_log._socket, "socket", lambda *args: fake)

    gway_log.configure_output(level="INFO")
    assert gway_log._current_source() == "gway"

    with gway_log._source_scope("recipe/deploy"):
        assert gway_log._current_source() == "recipe/deploy"
        gway_log.info("inside")

    assert gway_log._current_source() == "gway"
    gway_log.info("outside")

    assert fake.payloads[-2:] == [
        b"<14>recipe/deploy: inside",
        b"<14>gway: outside",
    ]


def test_source_scope_nests_and_restores_after_exception():
    assert gway_log._current_source() == "gway"

    with pytest.raises(RuntimeError):
        with gway_log._source_scope("recipe/outer"):
            assert gway_log._current_source() == "recipe/outer"
            with gway_log._source_scope("recipe/inner"):
                assert gway_log._current_source() == "recipe/inner"
                raise RuntimeError("boom")

    assert gway_log._current_source() == "gway"


def test_file_output_preserves_logical_source(tmp_path):
    handler = gway_log.configure_output(destination="file", root=tmp_path)

    with gway_log._source_scope("recipe/deploy"):
        gway_log.info("portable identity")
    handler.flush()

    payload = json.loads(
        (tmp_path / "logs" / "gway.log").read_text(encoding="utf-8")
    )
    assert payload["source"] == "recipe/deploy"
    assert payload["message"] == "portable identity"


def test_default_non_journal_output_is_durable_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(gway_log, "_journal_address", lambda: None)

    handler = gway_log.configure_output(root=tmp_path, level="INFO")
    gway_log.info("portable default")
    handler.flush()

    assert isinstance(handler, TimedRotatingFileHandler)
    payload = json.loads(
        (tmp_path / "logs" / "gway.log").read_text(encoding="utf-8")
    )
    assert payload["source"] == "gway"
    assert payload["message"] == "portable default"


def test_default_journal_output_does_not_dual_write_file(
    monkeypatch,
    tmp_path,
):
    fake = _FakeJournalSocket()
    monkeypatch.setattr(gway_log, "_journal_address", lambda: "/run/journal")
    monkeypatch.setattr(gway_log._socket, "socket", lambda *args: fake)

    handler = gway_log.configure_output(root=tmp_path, level="INFO")
    gway_log.info("journal only")

    assert isinstance(handler, gway_log._JournalHandler)
    assert fake.payloads == [b"<14>gway: journal only"]
    assert not (tmp_path / "logs" / "gway.log").exists()



def test_gateway_log_source_resolves_semantic_environment_binding(monkeypatch):
    from gway import Gateway

    monkeypatch.setenv("GWAY_LOG_SOURCE", "semantic-source")

    Gateway()

    assert gway_log._current_source() == "semantic-source"
