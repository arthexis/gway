from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import GwayPaths, default_paths
from .dispatcher.errors import DispatchError
from .project import Project

_STATE_VERSION = 1
_CONSUMER_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_LOG_TOKEN_ENV = "GWAY_LOG_TOKEN"
_LOG_DESTINATION_ENV = "GWAY_LOG_DESTINATION"


def _state_path(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers.json"


def _environment_dir(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers"


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _read_state(paths: GwayPaths) -> dict[str, object]:
    path = _state_path(paths)
    if not path.exists():
        return {"version": _STATE_VERSION, "bindings": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DispatchError(f"cannot read log consumer state {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
        raise DispatchError(f"unsupported log consumer state in {path}")
    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        raise DispatchError(f"unsupported log consumer state in {path}")
    return data


def _write_state(paths: GwayPaths, data: dict[str, object]) -> None:
    path = _state_path(paths)
    _private_directory(path.parent)
    temporary = path.with_suffix(".tmp")
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    path.chmod(0o600)


def normalize_consumers(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize singular/plural consumer arguments into safe unique names."""
    consumers: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            if not _CONSUMER_NAME.fullmatch(value):
                raise DispatchError(f"invalid log consumer name: {value!r}")
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            consumers.append(value)
    return tuple(consumers)


def _remote_destination(destinations: Sequence[str]) -> str:
    remote = [
        destination
        for destination in destinations
        if urlparse(destination).scheme.casefold() in {"http", "https"}
    ]
    if len(remote) != 1:
        raise DispatchError(
            "log consumers require exactly one HTTP(S) --to destination"
        )
    return remote[0]


def _token_valid(record: dict[str, object], listed: object) -> bool:
    token_id = record.get("token_id")
    token = record.get("token")
    if not isinstance(token_id, str) or not isinstance(token, str):
        return False
    if not isinstance(listed, list):
        return False
    metadata = next(
        (
            item
            for item in listed
            if isinstance(item, dict) and item.get("token_id") == token_id
        ),
        None,
    )
    if metadata is None or metadata.get("revoked_at") is not None:
        return False
    expires_at = metadata.get("expires_at")
    if not isinstance(expires_at, str):
        return False
    try:
        return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    except ValueError:
        return False


def _issue_token(dispatch: Callable[[str, Sequence[str]], object], destination: str) -> dict[str, object]:
    result = dispatch(
        "web",
        [
            "token",
            "--name",
            f"gway-consumers:{urlparse(destination).netloc or destination}",
            "--scope",
            "logs:ingest",
        ],
    )
    if not isinstance(result, dict):
        raise DispatchError("web token command did not return token metadata")
    token = result.get("token")
    token_id = result.get("token_id")
    if not isinstance(token, str) or not token or not isinstance(token_id, str) or not token_id:
        raise DispatchError("web token command did not return an ingest credential")
    return {"token": token, "token_id": token_id}


def _environment_contents(destination: str, token: str) -> str:
    if any(character in destination for character in "\r\n") or any(
        character in token for character in "\r\n"
    ):
        raise DispatchError("log consumer credentials must not contain newlines")
    # Both values are generated/configured as token/URL scalars. JSON string
    # quoting is accepted by systemd EnvironmentFile and keeps whitespace safe.
    return (
        f"{_LOG_DESTINATION_ENV}={json.dumps(destination)}\n"
        f"{_LOG_TOKEN_ENV}={json.dumps(token)}\n"
    )


def _write_environment(paths: GwayPaths, consumer: str, destination: str, token: str) -> Path:
    directory = _environment_dir(paths)
    _private_directory(directory)
    path = directory / f"{consumer.casefold()}.env"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_environment_contents(destination, token), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)
    return path


def configure_consumers(
    consumers: Sequence[str],
    destinations: Sequence[str],
    *,
    dispatch: Callable[[str, Sequence[str]], object],
    paths: GwayPaths | None = None,
) -> dict[str, object]:
    """Bind same-host consumers to one remotely exposed GWAY log service."""
    selected = normalize_consumers(consumers)
    if not selected:
        raise DispatchError("--consumer/--consumers requires at least one consumer")
    destination = _remote_destination(destinations)
    active_paths = paths or default_paths()
    state = _read_state(active_paths)
    bindings = state["bindings"]
    assert isinstance(bindings, dict)

    existing = bindings.get(destination)
    record = dict(existing) if isinstance(existing, dict) else {}
    listed: object = None
    if record:
        try:
            listed = dispatch("web", ["token", "--list"])
        except Exception:
            listed = None
    if not _token_valid(record, listed):
        try:
            credential = _issue_token(dispatch, destination)
        except Exception as exc:
            if isinstance(exc, DispatchError):
                raise
            raise DispatchError(
                "cannot issue local log consumer credential through the registered web project"
            ) from exc
        record.update(credential)

    token = record.get("token")
    token_id = record.get("token_id")
    assert isinstance(token, str)
    assert isinstance(token_id, str)

    # A consumer has one active local logging destination. Moving it to another
    # destination removes it from the old binding rather than leaving ambiguous
    # service credentials behind.
    selected_keys = {value.casefold() for value in selected}
    for other_destination, other in list(bindings.items()):
        if other_destination == destination or not isinstance(other, dict):
            continue
        values = other.get("consumers", [])
        if not isinstance(values, list):
            continue
        remaining = [
            value
            for value in values
            if isinstance(value, str) and value.casefold() not in selected_keys
        ]
        if remaining:
            other["consumers"] = remaining
        else:
            bindings.pop(other_destination, None)

    prior = record.get("consumers", [])
    combined = normalize_consumers(
        [*(value for value in prior if isinstance(value, str)), *selected]
        if isinstance(prior, list)
        else selected
    )
    record.update(
        {
            "provider": "web",
            "destination": destination,
            "consumers": list(combined),
        }
    )
    bindings[destination] = record
    _write_state(active_paths, state)
    for consumer in combined:
        _write_environment(active_paths, consumer, destination, token)

    # Make the credential immediately available to this process so the same
    # `log` operation can backfill and continue publishing the active run.
    os.environ[_LOG_TOKEN_ENV] = token
    os.environ[_LOG_DESTINATION_ENV] = destination
    return {
        "destination": destination,
        "consumers": list(combined),
        "token_id": token_id,
    }


def consumer_environment_file(
    project: Project,
    *,
    paths: GwayPaths | None = None,
) -> Path | None:
    """Return the private logging EnvironmentFile configured for a project."""
    active_paths = paths or default_paths()
    try:
        state = _read_state(active_paths)
    except DispatchError:
        return None
    bindings = state.get("bindings", {})
    if not isinstance(bindings, dict):
        return None
    identities = {value.casefold() for value in (project.name, *project.aliases)}
    for record in bindings.values():
        if not isinstance(record, dict):
            continue
        consumers = record.get("consumers", [])
        if not isinstance(consumers, list):
            continue
        for consumer in consumers:
            if isinstance(consumer, str) and consumer.casefold() in identities:
                path = _environment_dir(active_paths) / f"{consumer.casefold()}.env"
                return path if path.is_file() else None
    return None


__all__ = [
    "configure_consumers",
    "consumer_environment_file",
    "normalize_consumers",
]
