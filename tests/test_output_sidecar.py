import json
import subprocess
import sys

import pytest

from gway.globals import command_options
from gway.output import OutputWriteError, write_json_atomic


def _run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "gway", *map(str, args)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_output_sidecar_preserves_human_stdout(tmp_path):
    output = tmp_path / "result.json"

    completed = _run("-o", output, "resolve", "[site|MTY]")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "MTY"
    assert json.loads(output.read_text(encoding="utf-8")) == "MTY"


def test_output_sidecar_coexists_with_json_stdout(tmp_path):
    output = tmp_path / "result.json"

    completed = _run("-j", "-o", output, "resolve", "[site|MTY]")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == "MTY"
    assert json.loads(output.read_text(encoding="utf-8")) == "MTY"


def test_output_sidecar_records_final_recipe_result_not_rendering_envelope(tmp_path):
    recipe = tmp_path / "ci.rx"
    recipe.write_text(
        "resolve '[first|one]'\nresolve '[second|two]'\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"

    completed = _run("ci", "-o", output, cwd=tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "two"
    assert json.loads(output.read_text(encoding="utf-8")) == "two"


def test_output_sidecar_is_written_when_console_output_is_silent(tmp_path):
    output = tmp_path / "result.json"

    completed = _run("--silent", "-o", output, "resolve", "[site|MTY]")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert json.loads(output.read_text(encoding="utf-8")) == "MTY"


def test_output_sidecar_failure_is_nonzero_and_does_not_traceback(tmp_path):
    output = tmp_path / "missing" / "result.json"

    completed = _run("-o", output, "resolve", "[site|MTY]")

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "cannot write structured output" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert not output.exists()


def test_atomic_output_preserves_existing_file_on_serialization_failure(tmp_path):
    output = tmp_path / "result.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(OutputWriteError, match="cannot write structured output"):
        write_json_atomic(output, object())

    assert json.loads(output.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob(".result.json.*.tmp")) == []


def test_mcp_leading_globals_reject_output_sidecar_flag():
    with pytest.raises(ValueError, match="Unsupported global flag"):
        command_options("--output result.json help")

    with pytest.raises(ValueError, match="Unsupported global flag"):
        command_options("-o result.json help")
