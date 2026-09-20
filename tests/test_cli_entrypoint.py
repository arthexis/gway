import subprocess
import sys

import gway
from gway import Gateway


def test_import_gway():
    assert isinstance(gway.gw, Gateway)


def test_cli_help_runs():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "command-dispatch and composition core" in completed.stdout


def test_cli_expression_resolves_supplied_context():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "--expression",
            "[site]",
            "--site",
            "MTY",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "MTY"
