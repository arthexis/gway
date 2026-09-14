from __future__ import annotations

import json

from gway.explain import explain_scope, record
from gway.logging import configure, current_context


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
