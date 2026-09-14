from __future__ import annotations

import json
import os
from pathlib import Path

from gway.explain import explain_scope, record
from gway.logging import configure, current_context, current_run_id, write_event


def test_record_persists_without_explain(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "test-run")

    record("runtime.operation.start", "executing", operation="demo")

    events = (tmp_path / "test-run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(events[-1])
    assert event["run_id"] == "test-run"
    assert event["kind"] == "runtime.operation.start"
    assert event["data"]["operation"] == "demo"


def test_persistent_recording_does_not_enable_explain(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "quiet-run")

    with explain_scope(enabled=False) as trace:
        record("test.event", "persist me")

    assert trace == []
    assert (tmp_path / "quiet-run" / "events.jsonl").exists()


def test_configure_accumulates_tags_and_destinations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "configured-run")

    configure(tags=("watchtower",), to=("https://example.invalid/logs",))
    state = configure(tags=("ubuntu22", "watchtower"))

    assert state["tags"] == ["watchtower", "ubuntu22"]
    assert state["to"] == ["https://example.invalid/logs"]
    assert current_context()["path"] == str(tmp_path / "configured-run")


def test_run_id_change_resets_logging_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "first-run")
    configure(tags=("first",), to=("https://example.invalid/first",))

    monkeypatch.setenv("GWAY_RUN_ID", "second-run")
    state = configure(tags=("second",))

    assert state["run_id"] == "second-run"
    assert state["tags"] == ["second"]
    assert state["to"] == []


def test_invalid_inherited_run_id_cannot_escape_log_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "../outside")

    run_id = current_run_id()
    write_event("test.event", "safe")

    assert run_id != "../outside"
    assert (tmp_path / run_id / "events.jsonl").is_file()
    assert not (tmp_path.parent / "outside" / "events.jsonl").exists()


def test_logging_serialization_failures_are_non_fatal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "serialization-run")
    cyclic: list[object] = []
    cyclic.append(cyclic)

    write_event("test.event", "cyclic", {"value": cyclic})
    write_event("test.event", "healthy", {"value": "ok"})

    lines = (tmp_path / "serialization-run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "healthy"


def test_log_paths_are_owner_only(tmp_path, monkeypatch) -> None:
    if os.name == "nt":
        return
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "private-run")

    write_event("test.event", "private")

    run_path = tmp_path / "private-run"
    log_path = run_path / "events.jsonl"
    assert run_path.stat().st_mode & 0o777 == 0o700
    assert log_path.stat().st_mode & 0o777 == 0o600


def test_log_directory_creation_failure_is_non_fatal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("GWAY_RUN_ID", "readonly-run")

    original_mkdir = Path.mkdir

    def fail_mkdir(self, *args, **kwargs):
        if self.name == "readonly-run":
            raise PermissionError("read only")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    write_event("test.event", "ignored")
    assert current_context()["run_id"] == "readonly-run"
