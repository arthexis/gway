import subprocess
import sys

import gway
from gway import Gateway


def test_import_gway():
    assert gway.gw is not None
    assert isinstance(gway.gw, Gateway)


def test_gateway_constructs_without_bundled_projects():
    gateway = Gateway()
    assert gateway.projects() == []


def test_cli_help_runs():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "Dynamic Project CLI" in completed.stdout
