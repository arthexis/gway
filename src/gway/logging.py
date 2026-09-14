from __future__ import annotations

import json
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlparse

_RUN_ID_ENV = "GWAY_RUN_ID"
_LOG_DIR_ENV = "GWAY_LOG_DIR"

_run_id: ContextVar[str | None] = ContextVar("gway_log_run_id", default=None)
_tags: ContextVar[tuple[str, ...]] = ContextVar("gway_log_tags", default=())
_destinations: ContextVar[tuple[str, ...]] = ContextVar("gway_log_destinations", default=())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_root() -> Path:
    configured = os.environ.get(_LOG_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home).expanduser() / "gway" / "runs"
    return Path.home() / ".local" / "state" / "gway" / "runs"


def current_run_id() -> str:
    inherited = os.environ.get(_RUN_ID_ENV)
    run_id = _run_id.get()
    if inherited and inherited != run_id:
        run_id = inherited
        _run_id.set(run_id)
    if run_id is not None:
        return run_id
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{secrets.token_hex(3)}"
    _run_id.set(run_id)
    os.environ[_RUN_ID_ENV] = run_id
    return run_id


def run_directory() -> Path:
    path = _default_root() / current_run_id()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _destination_root(destination: str) -> Path | None:
    parsed = urlparse(destination)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            return None
        return Path(unquote(parsed.path)).expanduser()
    if parsed.scheme:
        return None
    return Path(destination).expanduser()


def _destination_log(destination: str) -> Path | None:
    root = _destination_root(destination)
    if root is None:
        return None
    return root / current_run_id() / "events.jsonl"


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()


def _backfill(destination: str) -> None:
    target = _destination_log(destination)
    source = run_directory() / "events.jsonl"
    if target is None or not source.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    except OSError:
        return


def configure(*, tags: tuple[str, ...] = (), to: tuple[str, ...] = ()) -> dict[str, object]:
    """Add metadata and synchronization destinations to the current run.

    Filesystem paths and file:// URLs are synchronized immediately. Other URI
    schemes are retained as metadata for transport plugins to implement later.
    """
    if tags:
        _tags.set(tuple(dict.fromkeys((*_tags.get(), *tags))))
    if to:
        additions = tuple(value for value in to if value not in _destinations.get())
        _destinations.set(tuple(dict.fromkeys((*_destinations.get(), *to))))
        for destination in additions:
            _backfill(destination)
    state = current_context()
    write_event("log.configure", "updated logging context", state)
    return state


def current_context() -> dict[str, object]:
    return {
        "run_id": current_run_id(),
        "path": str(run_directory()),
        "tags": list(_tags.get()),
        "to": list(_destinations.get()),
    }


def write_event(kind: str, message: str, data: Mapping[str, object] | None = None) -> None:
    """Append one crash-tolerant JSON Lines event locally and to configured sinks."""
    payload = {
        "timestamp": _now(),
        "run_id": current_run_id(),
        "kind": kind,
        "message": message,
        "tags": list(_tags.get()),
        "to": list(_destinations.get()),
        "data": dict(data or {}),
    }
    line = json.dumps(payload, default=str, ensure_ascii=False) + "\n"
    try:
        _append(run_directory() / "events.jsonl", line)
    except OSError:
        # Logging must never make an otherwise valid GWAY command fail.
        return

    for destination in _destinations.get():
        target = _destination_log(destination)
        if target is None:
            continue
        try:
            _append(target, line)
        except OSError:
            # A failed mirror must not affect the command or canonical log.
            continue
