from __future__ import annotations

import json
from pathlib import Path

import pytest

from gway.chain_context import chain_context_scope
from gway.dispatcher.errors import DispatchError
from gway.logs.command import run_log
from gway.logging import write_event
from gway.runtime import GwayRuntime


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_log_tags_and_filesystem_destination_mirror_events(tmp_path, monkeypatch) -> None:
    local = tmp_path / "local"
    mirror = tmp_path / "mirror"
    monkeypatch.setenv("GWAY_LOG_DIR", str(local))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-destination")

    state = run_log(["--tags", "watchtower,ubuntu22", "--to", str(mirror)])
    write_event("test.event", "after configuration", {"ok": True})

    assert state["tags"][-2:] == ["watchtower", "ubuntu22"]
    assert state["to"][-1] == str(mirror)

    local_events = _events(local / "test-log-destination" / "events.jsonl")
    mirrored_events = _events(mirror / "test-log-destination" / "events.jsonl")
    assert local_events == mirrored_events
    assert local_events[-1]["kind"] == "test.event"
    assert local_events[-1]["tags"][-2:] == ["watchtower", "ubuntu22"]


def test_log_destination_backfills_existing_run(tmp_path, monkeypatch) -> None:
    local = tmp_path / "local"
    mirror = tmp_path / "mirror"
    monkeypatch.setenv("GWAY_LOG_DIR", str(local))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-backfill")

    write_event("before.destination", "written before destination")
    run_log(["--to", str(mirror)])

    mirrored = _events(mirror / "test-log-backfill" / "events.jsonl")
    assert mirrored[0]["kind"] == "before.destination"
    assert mirrored[-1]["kind"] == "log.configure"


def test_log_resolves_recipe_context_sigils(tmp_path, monkeypatch) -> None:
    local = tmp_path / "local"
    mirror = tmp_path / "mirror"
    monkeypatch.setenv("GWAY_LOG_DIR", str(local))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-sigil")

    with chain_context_scope({"log_destination": str(mirror)}):
        state = run_log(["--to", "[log_destination]"])

    assert state["to"] == [str(mirror)]
    assert (mirror / "test-log-sigil" / "events.jsonl").exists()


def test_log_invalid_options_raise_dispatch_error() -> None:
    with pytest.raises(DispatchError, match="unrecognized log arguments"):
        run_log(["--bogus"])


def test_runtime_exposes_log_as_core_operation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "local"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-runtime-log")

    result = GwayRuntime().execute(["log", "--tags", "recipe", "--to", str(tmp_path / "out")])

    assert result["tags"][-1] == "recipe"
    assert result["to"][-1] == str(tmp_path / "out")
    assert (tmp_path / "out" / "test-runtime-log" / "events.jsonl").exists()


def test_log_without_options_reports_current_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "local"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-context")

    state = run_log([])

    assert state["run_id"] == "test-log-context"
    assert state["path"].endswith("test-log-context")
