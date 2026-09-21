import argparse

from gway.console import _run_cli
from gway.reload import ReloadCheckpoint, ReloadTransferred


class FinishedProcess:
    def __init__(self, returncode):
        self.returncode = returncode

    def wait(self):
        return self.returncode


def _args():
    return argparse.Namespace(
        debug=False,
        interactive=False,
        timed=False,
        verbose=False,
        silent=False,
        resume=None,
        recipe=None,
        expression=None,
        json=False,
    )


def _run_transferred_cli(monkeypatch, tmp_path, returncode):
    checkpoint = ReloadCheckpoint.create()
    process = FinishedProcess(returncode)

    def transfer(*args, **kwargs):
        raise ReloadTransferred(process, checkpoint, tmp_path / "rollback")

    monkeypatch.setattr("gway.console.process", transfer)
    return _run_cli(argparse.ArgumentParser(), _args(), ["reload"])


def test_cli_supervises_successful_reload_transfer(monkeypatch, tmp_path):
    assert _run_transferred_cli(monkeypatch, tmp_path, 0) == 0


def test_cli_propagates_positive_successor_exit_code(monkeypatch, tmp_path):
    assert _run_transferred_cli(monkeypatch, tmp_path, 7) == 7


def test_cli_maps_signal_style_successor_failure_to_one(monkeypatch, tmp_path):
    assert _run_transferred_cli(monkeypatch, tmp_path, -9) == 1
