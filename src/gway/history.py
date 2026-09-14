from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import logging as logging_module
from .logging import current_run_id


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    timestamp: str | None
    command: tuple[str, ...]
    projects: tuple[str, ...]
    status: str
    exit_code: int | None
    error: dict[str, object] | None
    events: tuple[dict[str, object], ...]

    def as_dict(self, *, include_events: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "command": list(self.command),
            "projects": list(self.projects),
            "status": self.status,
            "exit_code": self.exit_code,
            "error": self.error,
        }
        if include_events:
            result["events"] = list(self.events)
        return result


def _read_events(path: Path) -> tuple[dict[str, object], ...]:
    events: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ()
    for line in lines:
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return tuple(events)


def _event_data(event: dict[str, object]) -> dict[str, object]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _command(events: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    for kind, field in (
        ("execution.start", "argv"),
        ("chain.start", "tokens"),
        ("runtime.frame.enter", "tokens"),
    ):
        for event in events:
            if event.get("kind") != kind:
                continue
            value = _event_data(event).get(field)
            if isinstance(value, list):
                return tuple(str(item) for item in value)

    for event in events:
        if event.get("kind") != "dispatch.start":
            continue
        data = _event_data(event)
        value = data.get("tokens")
        project = data.get("project")
        if isinstance(value, list):
            tokens = tuple(str(item) for item in value)
            if isinstance(project, str):
                return (project, *tokens)
            return tokens
    return ()


def _record(run_id: str, events: tuple[dict[str, object], ...]) -> RunRecord | None:
    if not events:
        return None

    projects: list[str] = []
    for event in events:
        if event.get("kind") != "dispatch.start":
            continue
        project = _event_data(event).get("project")
        if isinstance(project, str) and project not in projects:
            projects.append(project)

    failures = [event for event in events if event.get("kind") == "execution.failure"]
    success_kinds = {"execution.success", "chain.result", "recipe.result", "command.result"}
    successes = [event for event in events if event.get("kind") in success_kinds]
    status = "failed" if failures else "succeeded" if successes else "incomplete"

    terminal = failures[-1] if failures else successes[-1] if successes else None
    terminal_data = _event_data(terminal) if terminal is not None else {}
    raw_exit_code = terminal_data.get("exit_code")
    exit_code = raw_exit_code if isinstance(raw_exit_code, int) else (0 if successes else None)

    error: dict[str, object] | None = None
    if failures:
        detail = next(
            (
                _event_data(event)
                for event in reversed(events)
                if any(key in _event_data(event) for key in ("error", "exception", "traceback"))
            ),
            terminal_data,
        )
        error = {
            key: detail[key]
            for key in ("exception", "error", "traceback")
            if key in detail
        } or None

    timestamp = events[0].get("timestamp")
    return RunRecord(
        run_id=run_id,
        timestamp=timestamp if isinstance(timestamp, str) else None,
        command=_command(events),
        projects=tuple(projects),
        status=status,
        exit_code=exit_code,
        error=error,
        events=events,
    )


def _directory_order(path: Path) -> tuple[float, str]:
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return modified, path.name


def iter_runs(*, exclude_current: bool = True) -> Iterator[RunRecord]:
    """Yield persisted GWAY runs newest first as structured records."""
    root = logging_module._default_root()
    if not root.exists():
        return
    current = current_run_id() if exclude_current else None
    try:
        directories = sorted(
            (path for path in root.iterdir() if path.is_dir()),
            key=_directory_order,
            reverse=True,
        )
    except OSError:
        return
    for directory in directories:
        if current is not None and directory.name == current:
            continue
        record = _record(directory.name, _read_events(directory / "events.jsonl"))
        if record is not None:
            yield record


def last_run(
    *,
    project: str | None = None,
    failed: bool | None = None,
    include_events: bool = False,
) -> dict[str, object] | None:
    """Return the newest persisted run matching structured history filters."""
    for record in iter_runs():
        if project is not None and project not in record.projects:
            continue
        if failed is True and record.status != "failed":
            continue
        if failed is False and record.status != "succeeded":
            continue
        return record.as_dict(include_events=include_events)
    return None


__all__ = ["RunRecord", "iter_runs", "last_run"]
