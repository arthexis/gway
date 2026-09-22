import json
import os
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


def test_cli_default_logging_uses_host_canonical_backend(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "log",
            "reconciliation-test",
            "--level",
            "INFO",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    log_path = tmp_path / "logs" / "gway.log"
    if os.path.exists("/run/systemd/journal/dev-log") or os.path.exists("/dev/log"):
        assert not log_path.exists()
    else:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        assert payload["source"] == "gway"
        assert payload["message"] == "reconciliation-test"


def test_cli_file_logging_remains_explicit_compatibility_option(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "--logfile",
            "file",
            "log",
            "reconciliation-test",
            "--level",
            "INFO",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    log_path = tmp_path / "logs" / "gway.log"
    assert log_path.is_file()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["level"] == "INFO"
    assert payload["source"] == "gway"
    assert payload["message"] == "reconciliation-test"


def test_cli_logfile_stdout_is_explicit_opt_in(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "--logfile",
            "stdout",
            "log",
            "visible-on-stdout",
            "--level",
            "INFO",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    assert "INFO gway [gway] visible-on-stdout" in completed.stdout
    assert completed.stderr == ""


def test_cli_logfile_stderr_is_explicit_opt_in(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "--logfile",
            "stderr",
            "log",
            "visible-on-stderr",
            "--level",
            "INFO",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert "INFO gway [gway] visible-on-stderr" in completed.stderr
