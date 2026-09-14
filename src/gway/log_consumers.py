from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
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


def _environment_dir_for_state(state_path: Path) -> Path:
    return state_path.parent / "log-consumers"


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


def _atomic_private_write(path: Path, payload: bytes) -> None:
    _private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_state(paths: GwayPaths, data: dict[str, object]) -> None:
    path = _state_path(paths)
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_private_write(path, payload)


@contextmanager
def _state_lock(paths: GwayPaths) -> Iterator[None]:
    """Serialize consumer-state transactions across GWAY processes."""
    path = _state_path(paths).with_suffix(".lock")
    _private_directory(path.parent)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            while True:
                try:
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


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


def _loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _remote_destination(destinations: Sequence[str]) -> str:
    remote: list[str] = []
    for destination in destinations:
        parsed = urlparse(destination)
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"}:
            continue
        if not parsed.netloc:
            raise DispatchError("log consumer HTTP(S) destination requires an authority")
        if scheme == "http" and not _loopback_host(parsed.hostname):
            raise DispatchError("log consumer HTTP destinations must use HTTPS unless loopback")
        remote.append(destination)
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
    # The provider must return the raw credential to this caller, but that result
    # must never be serialized by Dispatcher instrumentation into events.jsonl.
    from .dispatcher.dispatch import redact_command_results

    with redact_command_results():
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


def _write_environment(
    paths: GwayPaths,
    consumer: str,
    destination: str,
    token: str,
) -> tuple[Path, bool]:
    path = _environment_path(paths, consumer)
    contents = _environment_contents(destination, token)
    try:
        unchanged = path.read_text(encoding="utf-8") == contents
    except (FileNotFoundError, OSError):
        unchanged = False
    if unchanged:
        return path, False
    _atomic_private_write(path, contents.encode("utf-8"))
    return path, True


def _remove_environment(paths: GwayPaths, consumer: str) -> bool:
    try:
        _environment_path(paths, consumer).unlink()
        return True
    except FileNotFoundError:
        return False


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
    from .logging import retry_remote_destination

    for destination in destinations:
        token = publisher_token(destination, paths=paths)
        if token is not None:
            set_token(destination, token)
            retry_remote_destination(destination)


def _refresh_running_consumer_services(
    consumers: Sequence[str],
    resolve_consumer: ConsumerResolver | None,
) -> list[str]:
    """Restart installed consumer units after their persisted logging environment changes."""
    if resolve_consumer is None:
        return []
    from .service import ServiceError, ServiceManager

    projects: dict[str, Project] = {}
    for consumer in consumers:
        project = resolve_consumer(consumer)
        if project is not None:
            projects.setdefault(project.name.casefold(), project)

    refreshed: list[str] = []
    for project in projects.values():
        try:
            manager = ServiceManager(project, all_services=True)
        except ServiceError:
            continue
        for unit in manager.units:
            if not unit.unit_path.is_file():
                continue
            try:
                unit.restart()
            except Exception as exc:
                raise DispatchError(
                    f"updated log consumer environment but could not restart service {unit.unit_name}"
                ) from exc
            refreshed.append(unit.unit_name)
    return refreshed


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
    changed_consumers: set[str] = set()

    # Keep the full read-modify-write transaction serialized so independent GWAY
    # processes cannot lose each other's bindings or race on EnvironmentFiles.
    with _state_lock(active_paths):
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
                if _remove_environment(active_paths, value):
                    changed_consumers.add(value)
            if remaining:
                other["consumers"] = remaining
            else:
                bindings.pop(other_destination, None)

        prior = record.get("consumers", [])
        prior_values = (
            [value for value in prior if isinstance(value, str)]
            if isinstance(prior, list)
            else []
        )
        combined, _ = _canonical_consumers([*prior_values, *selected], resolve_consumer)
        combined_keys = {value.casefold() for value in combined}
        for previous in prior_values:
            if previous.casefold() not in combined_keys:
                if _remove_environment(active_paths, previous):
                    changed_consumers.add(previous)

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
            _, changed = _write_environment(active_paths, consumer, destination, token)
            if changed:
                changed_consumers.add(consumer)

    # Only a non-secret state-file path is exported for reload/exec continuity.
    # The bearer credential itself stays in private state and process-local HTTP
    # publisher context, so unrelated managed commands/subprocesses do not inherit it.
    os.environ[_STATE_PATH_ENV] = str(_state_path(active_paths))
    activate_publisher_tokens((destination,), paths=active_paths)
    refreshed_services = (
        _refresh_running_consumer_services(sorted(changed_consumers), resolve_consumer)
        if changed_consumers
        else []
    )
    result: dict[str, object] = {
        "destination": destination,
        "consumers": list(combined),
        "token_id": token_id,
    }
    if refreshed_services:
        result["refreshed_services"] = refreshed_services
    return result


def consumer_environment_file(
    project: Project,
    *,
    paths: GwayPaths | None = None,
) -> Path | None:
    """Return the private logging EnvironmentFile configured for a project."""
    state_path = _binding_state_path(paths)
    try:
        state = _read_state_path(state_path)
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
    path = _environment_dir_for_state(state_path) / f"{consumer.casefold()}.env"
    return path if path.is_file() else None


__all__ = [
    "activate_publisher_tokens",
    "configure_consumers",
    "consumer_environment_file",
    "normalize_consumers",
    "publisher_token",
]
