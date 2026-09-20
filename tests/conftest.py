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
