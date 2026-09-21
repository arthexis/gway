import subprocess

import pytest

from gway.gateway import Gateway
from gway.ingestion.proc import ProcessResult


def test_explicit_process_ingestion_preserves_argv(tmp_path):
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    tool.chmod(0o755)
    runtime = Gateway()

    runtime.ingest(str(tool), kind="proc")
    result = runtime("tool first --flag value --switch")

    assert isinstance(result, ProcessResult)
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["first", "--flag", "value", "--switch"]


def test_recipe_surface_can_ingest_process(monkeypatch, tmp_path):
    tool = tmp_path / "recipe-tool"
    tool.symlink_to("/bin/echo")
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ.get('PATH', '')}")
    runtime = Gateway()

    runtime("ingest recipe-tool --kind proc")
    result = runtime("recipe-tool recipe")

    assert result.stdout.strip() == "recipe"


def test_bare_name_falls_back_to_path_executable(monkeypatch, tmp_path):
    tool = tmp_path / "gway-proc-test"
    tool.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ.get('PATH', '')}")
    runtime = Gateway()

    runtime.ingest("gway-proc-test")
    result = runtime("gway-proc-test")

    assert result.stdout.strip() == "ok"


def test_python_name_wins_over_same_named_executable(monkeypatch, tmp_path):
    executable = tmp_path / "json"
    executable.write_text("#!/bin/sh\necho process\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ.get('PATH', '')}")
    runtime = Gateway()

    wrapped = runtime.ingest("json")

    assert wrapped
    assert all(getattr(item, "__gway_source_kind__", None) != "proc" for item in wrapped)


def test_nonzero_process_exit_keeps_failure_semantics(tmp_path):
    tool = tmp_path / "bad"
    tool.write_text("#!/bin/sh\necho boom >&2\nexit 7\n", encoding="utf-8")
    tool.chmod(0o755)
    runtime = Gateway()
    runtime.ingest(str(tool), kind="proc")

    with pytest.raises(subprocess.CalledProcessError) as error:
        runtime("bad")

    assert error.value.returncode == 7
    assert error.value.stderr.strip() == "boom"
