import sys
from types import SimpleNamespace

import pytest

import gway.log as gway_log
from gway import Gateway
from gway.console import cli_main


@pytest.fixture
def gateway():
    runtime = Gateway()
    runtime.context.clear()
    runtime.results.clear()
    return runtime


@pytest.fixture
def restore_gway_log_level():
    """Restore the parent Gway logger level after one test."""
    previous = gway_log.logger.level
    yield gway_log.logger
    gway_log.logger.setLevel(previous)


@pytest.fixture
def run_cli(monkeypatch, capsys):
    """Run the CLI with isolated argv and return status/stdout/stderr."""

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["gway", *args])
        status = cli_main()
        captured = capsys.readouterr()
        return status, captured.out, captured.err

    return run


@pytest.fixture
def host_calls(monkeypatch):
    """Capture commands sent through the shared privileged host boundary."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.host.subprocess.run", fake_run)
    return calls


@pytest.fixture
def rollback_paths(tmp_path):
    """Return a source file and absent destination for rollback tests."""
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    return source, destination


@pytest.fixture
def record_rollbacks(gateway, monkeypatch):
    """Record journal rollback calls while preserving real rollback behavior."""
    calls = []
    original = gateway.journal.rollback

    def rollback(name):
        calls.append(name)
        return original(name)

    monkeypatch.setattr(gateway.journal, "rollback", rollback)
    return calls


@pytest.fixture
def journal_entry(gateway):
    """Return a journal entry by name and index without duplicating lookup boilerplate."""

    def lookup(name="deploy", index=0):
        return gateway.journal.require_open(name).entries[index]

    return lookup
