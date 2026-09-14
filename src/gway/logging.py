from __future__ import annotations

import json
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

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


def configure(*, tags: tuple[str, ...] = (), to: tuple[str, ...] = ()) -> dict[str, object]:
    """Add metadata and future sync destinations to the current run."""
    if tags:
        _tags.set(tuple(dict.fromkeys((*_tags.get(), *tags))))
    if to:
        _destinations.set(tuple(dict.fromkeys((*_destinations.get(), *to))))
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
    """Append one crash-tolerant JSON Lines event to the current run."""
    payload = {
        "timestamp": _now(),
        "run_id": current_run_id(),
        "kind": kind,
        "message": message,
        "tags": list(_tags.get()),
        "to": list(_destinations.get()),
        "data": dict(data or {}),
    }
    path = run_directory() / "events.jsonl"
    try:
        with path.open("a", encoding="utf-8") as stream:
            json.dump(payload, stream, default=str, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
    except OSError:
        # Logging must never make an otherwise valid GWAY command fail.
        return
