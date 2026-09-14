from __future__ import annotations

import json
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlparse

from .log_http import clear_tokens, publish as publish_http

_RUN_ID_ENV = "GWAY_RUN_ID"
_LOG_DIR_ENV = "GWAY_LOG_DIR"
_LOG_CONTEXT_ENV = "GWAY_LOG_CONTEXT"
_LOG_DESTINATION_ENV = "GWAY_LOG_DESTINATION"

_run_id: ContextVar[str | None] = ContextVar("gway_log_run_id", default=None)
_tags: ContextVar[tuple[str, ...]] = ContextVar("gway_log_tags", default=())
_destinations: ContextVar[tuple[str, ...]] = ContextVar("gway_log_destinations", default=())
_failed_remote_destinations: ContextVar[frozenset[str]] = ContextVar(
    "gway_log_failed_remote_destinations", default=frozenset()
)


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


def _default_destinations() -> tuple[str, ...]:
    value = os.environ.get(_LOG_DESTINATION_ENV, "").strip()
    return (value,) if value else ()


def _safe_run_id(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    path = Path(value)
    return not path.is_absolute() and path.name == value and "/" not in value and "\\" not in value


def _activate_private_tokens() -> None:
    try:
        from .log_consumers import activate_publisher_tokens

        activate_publisher_tokens(_destinations.get())
    except Exception:
        # Logging remains best-effort. A corrupt/unavailable optional consumer
        # binding must never turn a normal GWAY command into a failure.
        return


def _reset_run_context() -> None:
    _tags.set(())
    _destinations.set(_default_destinations())
    _failed_remote_destinations.set(frozenset())
    clear_tokens()
    _activate_private_tokens()


def _persist_run_context(run_id: str) -> None:
    os.environ[_LOG_CONTEXT_ENV] = json.dumps(
        {"run_id": run_id, "tags": list(_tags.get()), "to": list(_destinations.get())},
        ensure_ascii=False,
    )


def _restore_run_context(run_id: str) -> None:
    _reset_run_context()
    raw = os.environ.get(_LOG_CONTEXT_ENV)
    if raw:
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            state = None
        if isinstance(state, dict) and state.get("run_id") == run_id:
            tags = state.get("tags", [])
            destinations = state.get("to", [])
            if isinstance(tags, list) and all(isinstance(value, str) for value in tags):
                _tags.set(tuple(dict.fromkeys(tags)))
            if isinstance(destinations, list) and all(isinstance(value, str) for value in destinations):
                _destinations.set(tuple(dict.fromkeys((*_destinations.get(), *destinations))))
    # Consumer state stores only a non-secret path in the inherited environment;
    # reload/exec can therefore recover the process-local publisher credential
    # without exporting the bearer token to unrelated subprocesses.
    _activate_private_tokens()


def current_run_id() -> str:
    inherited = os.environ.get(_RUN_ID_ENV)
    run_id = _run_id.get()
    if inherited and inherited != run_id:
        if _safe_run_id(inherited):
            run_id = inherited
            _run_id.set(run_id)
            _restore_run_context(run_id)
        else:
            os.environ.pop(_RUN_ID_ENV, None)
            inherited = None
    if run_id is not None:
        return run_id
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{secrets.token_hex(3)}"
    _run_id.set(run_id)
    _reset_run_context()
    os.environ[_RUN_ID_ENV] = run_id
    _persist_run_context(run_id)
    return run_id


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def run_directory() -> Path:
    path = _default_root() / current_run_id()
    try:
        _ensure_private_directory(path)
    except OSError:
        pass
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


def _append(path: Path, line: bytes) -> None:
    _ensure_private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, line)
    finally:
        os.close(descriptor)


def _replace(path: Path, data: bytes) -> None:
    _ensure_private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, data)
    finally:
        os.close(descriptor)


def _publish_remote(destination: str, data: bytes) -> None:
    if destination in _failed_remote_destinations.get():
        return
    if publish_http(destination, current_run_id(), data):
        return
    _failed_remote_destinations.set(_failed_remote_destinations.get() | {destination})


def _backfill(destination: str) -> None:
    source = run_directory() / "events.jsonl"
    if not source.exists():
        return
    try:
        data = source.read_bytes()
    except OSError:
        return
    target = _destination_log(destination)
    if target is not None:
        try:
            _replace(target, data)
        except OSError:
            pass
        return
    _publish_remote(destination, data)


def configure(*, tags: tuple[str, ...] = (), to: tuple[str, ...] = ()) -> dict[str, object]:
    """Add metadata and synchronization destinations to the current run."""
    run_id = current_run_id()
    if tags:
        _tags.set(tuple(dict.fromkeys((*_tags.get(), *tags))))
    if to:
        additions = tuple(value for value in to if value not in _destinations.get())
        _destinations.set(tuple(dict.fromkeys((*_destinations.get(), *to))))
        _activate_private_tokens()
        for destination in additions:
            _backfill(destination)
    _persist_run_context(run_id)
    state = current_context()
    write_event("log.configure", "updated logging context", state)
    return state


def current_context() -> dict[str, object]:
    run_id = current_run_id()
    return {
        "run_id": run_id,
        "path": str(run_directory()),
        "tags": list(_tags.get()),
        "to": list(_destinations.get()),
    }


def write_event(kind: str, message: str, data: Mapping[str, object] | None = None) -> None:
    """Append one crash-tolerant JSON Lines event locally and to configured sinks."""
    try:
        payload = {
            "timestamp": _now(),
            "run_id": current_run_id(),
            "kind": kind,
            "message": message,
            "tags": list(_tags.get()),
            "to": list(_destinations.get()),
            "data": dict(data or {}),
        }
        line = (json.dumps(payload, default=str, ensure_ascii=False) + "\n").encode("utf-8")
        _append(run_directory() / "events.jsonl", line)
    except (OSError, TypeError, ValueError):
        return

    for destination in _destinations.get():
        target = _destination_log(destination)
        if target is not None:
            try:
                _append(target, line)
            except OSError:
                pass
            continue
        _publish_remote(destination, line)
