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
_STATE_PATH_ENV = "GWAY_LOG_CONSUMER_STATE"
ConsumerResolver = Callable[[str], Project | None]


def _state_path(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers.json"


def _environment_dir(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers"


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _read_state_path(path: Path) -> dict[str, object]:
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


def _read_state(paths: GwayPaths) -> dict[str, object]:
    return _read_state_path(_state_path(paths))


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


def _consumer_identity(
    value: str,
    resolve_consumer: ConsumerResolver | None,
) -> tuple[str, set[str]]:
    project = resolve_consumer(value) if resolve_consumer is not None else None
    if project is None:
        return value, {value.casefold()}
    identities = {item.casefold() for item in (project.name, *project.aliases)}
    return project.name, identities


def _canonical_consumers(
    values: Sequence[str],
    resolve_consumer: ConsumerResolver | None,
) -> tuple[tuple[str, ...], set[str]]:
    canonical: list[str] = []
    identities: set[str] = set()
    seen: set[str] = set()
    for value in normalize_consumers(values):
        name, aliases = _consumer_identity(value, resolve_consumer)
        identities.update(aliases)
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            canonical.append(name)
    return tuple(canonical), identities


def _remote_destination(destinations: Sequence[str]) -> str:
    remote = [
        destination
        for destination in destinations
        if urlparse(destination).scheme.casefold() in {"http", "https"}
    ]
    if len(remote) != 1:
        raise DispatchError("log consumers require exactly one HTTP(S) --to destination")
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
        expiry = datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def _issue_token(
    dispatch: Callable[[str, Sequence[str]], object],
    destination: str,
) -> dict[str, object]:
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


def _environment_path(paths: GwayPaths, consumer: str) -> Path:
    return _environment_dir(paths) / f"{consumer.casefold()}.env"


def _write_environment(paths: GwayPaths, consumer: str, destination: str, token: str) -> Path:
    directory = _environment_dir(paths)
    _private_directory(directory)
    path = _environment_path(paths, consumer)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_environment_contents(destination, token), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)
    return path


def _remove_environment(paths: GwayPaths, consumer: str) -> None:
    try:
        _environment_path(paths, consumer).unlink()
    except FileNotFoundError:
        pass


def _binding_state_path(paths: GwayPaths | None = None) -> Path:
    if paths is not None:
        return _state_path(paths)
    inherited = os.environ.get(_STATE_PATH_ENV)
    if inherited:
        return Path(inherited).expanduser()
    return _state_path(default_paths())


def publisher_token(destination: str, *, paths: GwayPaths | None = None) -> str | None:
    """Read one private same-host publisher token without exporting it globally."""
    try:
        state = _read_state_path(_binding_state_path(paths))
    except DispatchError:
        return None
    bindings = state.get("bindings", {})
    if not isinstance(bindings, dict):
        return None
    record = bindings.get(destination)
    if not isinstance(record, dict):
        return None
    token = record.get("token")
    return token if isinstance(token, str) and token else None


def activate_publisher_tokens(
    destinations: Sequence[str],
    *,
    paths: GwayPaths | None = None,
) -> None:
    """Load private consumer credentials into process-local HTTP publisher state."""
    from .log_http import set_token

    for destination in destinations:
        token = publisher_token(destination, paths=paths)
        if token is not None:
            set_token(destination, token)


def configure_consumers(
    consumers: Sequence[str],
    destinations: Sequence[str],
    *,
    dispatch: Callable[[str, Sequence[str]], object],
    paths: GwayPaths | None = None,
    resolve_consumer: ConsumerResolver | None = None,
) -> dict[str, object]:
    """Bind same-host consumers to one remotely exposed GWAY log service."""
    selected, selected_identities = _canonical_consumers(consumers, resolve_consumer)
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

    # A project identity (canonical name or alias) has one active local logging
    # destination. Resolve stored aliases where possible before moving it.
    for other_destination, other in list(bindings.items()):
        if other_destination == destination or not isinstance(other, dict):
            continue
        values = other.get("consumers", [])
        if not isinstance(values, list):
            continue
        remaining: list[str] = []
        removed: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            _, identities = _consumer_identity(value, resolve_consumer)
            if identities & selected_identities:
                removed.append(value)
            else:
                remaining.append(value)
        for value in removed:
            _remove_environment(active_paths, value)
        if remaining:
            other["consumers"] = remaining
        else:
            bindings.pop(other_destination, None)

    prior = record.get("consumers", [])
    prior_values = [value for value in prior if isinstance(value, str)] if isinstance(prior, list) else []
    combined, _ = _canonical_consumers([*prior_values, *selected], resolve_consumer)
    combined_keys = {value.casefold() for value in combined}
    for previous in prior_values:
        if previous.casefold() not in combined_keys:
            _remove_environment(active_paths, previous)

    record.update(
        {
            "provider": "web",
            "destination": destination,
            "consumers": list(combined),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    bindings[destination] = record
    _write_state(active_paths, state)
    for consumer in combined:
        _write_environment(active_paths, consumer, destination, token)

    # Only a non-secret state-file path is exported for reload/exec continuity.
    # The bearer credential itself stays in private state and process-local HTTP
    # publisher context, so unrelated managed commands/subprocesses do not inherit it.
    os.environ[_STATE_PATH_ENV] = str(_state_path(active_paths))
    activate_publisher_tokens((destination,), paths=active_paths)
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
    matches: list[str] = []
    for destination, record in bindings.items():
        if not isinstance(record, dict):
            continue
        consumers = record.get("consumers", [])
        if not isinstance(consumers, list):
            continue
        if any(
            isinstance(consumer, str) and consumer.casefold() in identities
            for consumer in consumers
        ):
            matches.append(destination)
    if len(matches) > 1:
        raise DispatchError(
            f"log consumer {project.name!r} matches multiple destinations: {', '.join(sorted(matches))}"
        )
    if not matches:
        return None
    record = bindings[matches[0]]
    assert isinstance(record, dict)
    consumers = record.get("consumers", [])
    assert isinstance(consumers, list)
    consumer = next(
        value
        for value in consumers
        if isinstance(value, str) and value.casefold() in identities
    )
    path = _environment_path(active_paths, consumer)
    return path if path.is_file() else None


__all__ = [
    "activate_publisher_tokens",
    "configure_consumers",
    "consumer_environment_file",
    "normalize_consumers",
    "publisher_token",
]
