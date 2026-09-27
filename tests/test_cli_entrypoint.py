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


def test_cli_resolve_value_uses_inline_fallback():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "resolve",
            "[site|MTY]",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "MTY"



def test_cli_no_longer_exposes_expression_flag():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert "--expression" not in completed.stdout
    assert "-e " not in completed.stdout


def test_cli_resolve_reports_wire_sampler_without_executing_it():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--json", "resolve", "wire", "watchtower"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["kind"] == "recipe"
    assert payload["target"].endswith("sampler/wire/watchtower.rx")

def test_cli_resolve_single_plain_token_is_command_introspection():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--json", "resolve", "help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["kind"] == "operation"


def test_cli_resolve_keeps_target_options_opaque():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "--json", "resolve", "log", "message", "--level", "INFO"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["kind"] == "operation"
    assert payload["target"].replace(".", " ") == "log"
    assert "--level" in payload["arguments"]


def test_cli_resolve_does_not_execute_dash_suffix(tmp_path):
    marker = tmp_path / "executed"
    command = [
        sys.executable, "-m", "gway", "--json", "resolve",
        "log", "message", "-", "path", str(marker),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()


def test_cli_lookup_error_is_concise_without_traceback(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "security",
            "token",
            "create",
            "test-client",
            "missing-scope",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr.strip() == "gway: Unknown security scope: missing-scope"
    assert "Traceback" not in completed.stderr


def test_cli_debug_preserves_lookup_traceback(tmp_path):
    env = os.environ.copy()
    env["GWAY_DATA_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gway",
            "--debug",
            "security",
            "token",
            "create",
            "test-client",
            "missing-scope",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode != 0
    assert "Traceback" in completed.stderr
    assert "Unknown security scope: missing-scope" in completed.stderr


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
