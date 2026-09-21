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


def test_cli_supervises_successful_reload_transfer(monkeypatch, tmp_path):
    checkpoint = ReloadCheckpoint.create()
    process = FinishedProcess(0)

    def transfer(*args, **kwargs):
        raise ReloadTransferred(process, checkpoint, tmp_path / "rollback")

    monkeypatch.setattr("gway.console.process", transfer)

    assert _run_cli(argparse.ArgumentParser(), _args(), ["reload"]) == 0


def test_cli_propagates_positive_successor_exit_code(monkeypatch, tmp_path):
    checkpoint = ReloadCheckpoint.create()
    process = FinishedProcess(7)

    def transfer(*args, **kwargs):
        raise ReloadTransferred(process, checkpoint, tmp_path / "rollback")

    monkeypatch.setattr("gway.console.process", transfer)

    assert _run_cli(argparse.ArgumentParser(), _args(), ["reload"]) == 7


def test_cli_maps_signal_style_successor_failure_to_one(monkeypatch, tmp_path):
    checkpoint = ReloadCheckpoint.create()
    process = FinishedProcess(-9)

    def transfer(*args, **kwargs):
        raise ReloadTransferred(process, checkpoint, tmp_path / "rollback")

    monkeypatch.setattr("gway.console.process", transfer)

    assert _run_cli(argparse.ArgumentParser(), _args(), ["reload"]) == 1
