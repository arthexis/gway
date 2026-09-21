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
    assert gway_log.default_log_path(root=tmp_path) == (
        tmp_path / "logs" / "gway.log"
    )


def test_file_output_rotates_daily_with_thirty_backups(tmp_path):
    handler = gway_log.configure_output(root=tmp_path)

    assert isinstance(handler, TimedRotatingFileHandler)
    assert Path(handler.baseFilename) == tmp_path / "logs" / "gway.log"
    assert handler.when == "MIDNIGHT"
    assert handler.interval == 24 * 60 * 60
    # Twenty-nine archives plus the current file keeps at most 30 days.\n    assert handler.backupCount == 29\n    assert handler.suffix == "%Y-%m-%d"
    assert handler.level == logging.INFO


def test_file_output_persists_info_without_console_output(tmp_path, capsys):
    gway_log.configure_output(root=tmp_path)

    gway_log.info("reconciliation complete")
    for handler in gway_log.logger.handlers:
        handler.flush()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    text = (tmp_path / "logs" / "gway.log").read_text(encoding="utf-8")
    assert "INFO gway reconciliation complete" in text


@pytest.mark.parametrize(\n    ("destination", "stream"),\n    [("stdout", "out"), ("stderr", "err")],\n)
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
    assert "custom destination" in path.read_text(encoding="utf-8")
    assert handler.level == logging.WARNING
