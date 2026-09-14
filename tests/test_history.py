from __future__ import annotations

import json
from pathlib import Path

from gway.history import last_run
from gway.log_command import run_log


def _write_run(root: Path, run_id: str, events: list[dict[str, object]]) -> None:
    path = root / run_id
    path.mkdir(parents=True)
    with (path / "events.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event) + "\n")


def _event(kind: str, data: dict[str, object], timestamp: str) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "run_id": "fixture",
        "kind": kind,
        "message": kind,
        "tags": [],
        "to": [],
        "data": data,
    }


def test_last_failed_run_filters_by_project(tmp_path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setenv("GWAY_LOG_DIR", str(root))
    monkeypatch.setenv("GWAY_RUN_ID", "query-run")

    _write_run(
        root,
        "older-epaper",
        [
            _event("chain.start", {"tokens": ["epaper", "write", "hello"]}, "2026-09-14T10:00:00+00:00"),
            _event("dispatch.start", {"project": "epaper", "tokens": ["write", "hello"]}, "2026-09-14T10:00:01+00:00"),
            _event(
                "execution.failure",
                {"exit_code": 2, "exception": "ImportError", "error": "missing PIL"},
                "2026-09-14T10:00:02+00:00",
            ),
        ],
    )
    _write_run(
        root,
        "newer-wire",
        [
            _event("chain.start", {"tokens": ["wire", "status"]}, "2026-09-14T11:00:00+00:00"),
            _event("dispatch.start", {"project": "wire", "tokens": ["status"]}, "2026-09-14T11:00:01+00:00"),
            _event("execution.failure", {"exit_code": 2}, "2026-09-14T11:00:02+00:00"),
        ],
    )

    result = last_run(project="epaper", failed=True, include_events=True)

    assert result is not None
    assert result["run_id"] == "older-epaper"
    assert result["command"] == ["epaper", "write", "hello"]
    assert result["projects"] == ["epaper"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert result["error"] == {"exception": "ImportError", "error": "missing PIL"}
    assert len(result["events"]) == 3


def test_log_last_exposes_structured_history(tmp_path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setenv("GWAY_LOG_DIR", str(root))
    monkeypatch.setenv("GWAY_RUN_ID", "query-run")
    _write_run(
        root,
        "failed-epaper",
        [
            _event("dispatch.start", {"project": "epaper", "tokens": ["write"]}, "2026-09-14T12:00:00+00:00"),
            _event("execution.failure", {"exit_code": 2}, "2026-09-14T12:00:01+00:00"),
        ],
    )

    result = run_log(["--last", "--failed", "--project", "epaper"])

    assert result["run_id"] == "failed-epaper"
    assert result["status"] == "failed"
    assert result["projects"] == ["epaper"]


def test_successful_run_is_available_without_failed_filter(tmp_path, monkeypatch) -> None:
    root = tmp_path / "runs"
    monkeypatch.setenv("GWAY_LOG_DIR", str(root))
    monkeypatch.setenv("GWAY_RUN_ID", "query-run")
    _write_run(
        root,
        "successful-run",
        [
            _event("chain.start", {"tokens": ["epaper", "clear"]}, "2026-09-14T13:00:00+00:00"),
            _event("dispatch.start", {"project": "epaper", "tokens": ["clear"]}, "2026-09-14T13:00:01+00:00"),
            _event("chain.result", {"result": True}, "2026-09-14T13:00:02+00:00"),
        ],
    )

    result = last_run(project="epaper")

    assert result is not None
    assert result["status"] == "succeeded"
    assert result["exit_code"] == 0
