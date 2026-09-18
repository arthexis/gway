from __future__ import annotations

import ipaddress
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import GwayPaths, default_paths
from .dispatcher.errors import DispatchError
from .logs.binding import PublisherBinding
from .logs.consumers import (
    ConsumerResolver,
    canonical_consumers,
    consumer_identity,
    normalize_consumers,
)
from .logs.interface import LogPublisherProvider
from .logs.providers import ProviderResolver, resolve_provider
from .logs.state import (
    atomic_private_write,
    read_state,
    read_state_path,
    state_lock,
    state_path,
    write_state,
)
from .project import Project
from .service.attachments import attach_environment_files, detach_environment_files

_LOG_TOKEN_ENV = "GWAY_LOG_TOKEN"
_LOG_DESTINATION_ENV = "GWAY_LOG_DESTINATION"
_STATE_PATH_ENV = "GWAY_LOG_CONSUMER_STATE"


def _environment_dir(paths: GwayPaths) -> Path:
    return paths.data_dir / "log-consumers"


def _environment_dir_for_state(state_path: Path) -> Path:
    return state_path.parent / "log-consumers"


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


def _binding_token_valid(binding: PublisherBinding, listed: object) -> bool:
    token_id = binding.metadata.get("token_id")
    token = binding.environment.get(_LOG_TOKEN_ENV)
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
) -> dict[str, str]:
    # Temporary compatibility provider behavior. G5 moves this lifecycle behind
    # the Web provider implementation.
    from .dispatcher.outcome import redact_command_results

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


def _publisher_binding(record: Mapping[str, object], destination: str) -> PublisherBinding | None:
    stored = record.get("publisher")
    if isinstance(stored, Mapping):
        binding = PublisherBinding.from_record(stored)
        if binding is not None:
            return binding

    # Read legacy records during the transition without making the generic
    # binding format understand Web token semantics.
    token = record.get("token")
    token_id = record.get("token_id")
    provider = record.get("provider")
    if (
        provider == "web"
        and isinstance(token, str)
        and token
        and isinstance(token_id, str)
        and token_id
    ):
        return PublisherBinding(
            provider="web",
            destination=destination,
            environment={
                _LOG_DESTINATION_ENV: destination,
                _LOG_TOKEN_ENV: token,
            },
            metadata={"token_id": token_id},
        )
    return None


class _LegacyWebProvider:
    """Compatibility provider until GWAY Web implements the shared interface."""

    name = "web"

    def __init__(self, dispatch: Callable[[str, Sequence[str]], object]) -> None:
        self.dispatch = dispatch

    def provision(
        self,
        *,
        destination: str,
        consumer: str,
        service=None,
        current: PublisherBinding | None = None,
    ) -> PublisherBinding:
        listed: object = None
        if current is not None:
            try:
                listed = self.dispatch("web", ["token", "--list"])
            except Exception:
                listed = None
        if current is not None and _binding_token_valid(current, listed):
            return current

        try:
            credential = _issue_token(self.dispatch, destination)
        except Exception as exc:
            if isinstance(exc, DispatchError):
                raise
            raise DispatchError(
                "cannot issue local log consumer credential through the registered web project"
            ) from exc
        return PublisherBinding(
            provider=self.name,
            destination=destination,
            environment={
                _LOG_DESTINATION_ENV: destination,
                _LOG_TOKEN_ENV: credential["token"],
            },
            metadata={"token_id": credential["token_id"]},
        )


def _select_provider(
    name: str,
    *,
    dispatch: Callable[[str, Sequence[str]], object],
    provider_resolver: ProviderResolver | None,
) -> LogPublisherProvider:
    if provider_resolver is not None:
        return resolve_provider(name, provider_resolver)
    if name.casefold() == "web":
        return _LegacyWebProvider(dispatch)
    raise DispatchError(f"unknown log publisher provider: {name}")


def _environment_contents(environment: Mapping[str, str]) -> str:
    lines: list[str] = []
    for key, value in environment.items():
        if not key or any(character in key for character in "=\r\n"):
            raise DispatchError("log publisher environment keys must be safe names")
        if any(character in value for character in "\r\n"):
            raise DispatchError("log publisher environment values must not contain newlines")
        lines.append(f"{key}={json.dumps(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _environment_path(paths: GwayPaths, consumer: str) -> Path:
    return _environment_dir(paths) / f"{consumer.casefold()}.env"


def _write_environment(
    paths: GwayPaths,
    consumer: str,
    environment: Mapping[str, str],
) -> tuple[Path, bool]:
    path = _environment_path(paths, consumer)
    contents = _environment_contents(environment)
    try:
        unchanged = path.read_text(encoding="utf-8") == contents
    except (FileNotFoundError, OSError):
        unchanged = False
    if unchanged:
        return path, False
    atomic_private_write(path, contents.encode("utf-8"))
    return path, True


def _remove_environment(paths: GwayPaths, consumer: str) -> bool:
    try:
        _environment_path(paths, consumer).unlink()
        return True
    except FileNotFoundError:
        return False


def _binding_state_path(paths: GwayPaths | None = None) -> Path:
    if paths is not None:
        return state_path(paths)
    inherited = os.environ.get(_STATE_PATH_ENV)
    if inherited:
        return Path(inherited).expanduser()
    return state_path(default_paths())


def publisher_token(destination: str, *, paths: GwayPaths | None = None) -> str | None:
    """Read one private same-host publisher token without exporting it globally."""
    try:
        state = read_state_path(_binding_state_path(paths))
    except DispatchError:
        return None
    bindings = state.get("bindings", {})
    if not isinstance(bindings, dict):
        return None
    record = bindings.get(destination)
    if not isinstance(record, dict):
        return None
    binding = _publisher_binding(record, destination)
    if binding is not None:
        token = binding.environment.get(_LOG_TOKEN_ENV)
        return token if isinstance(token, str) and token else None
    return None


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
    provider: str = "web",
    provider_resolver: ProviderResolver | None = None,
) -> dict[str, object]:
    """Bind same-host consumers to one remotely exposed GWAY log service."""
    selected, selected_identities = canonical_consumers(consumers, resolve_consumer)
    if not selected:
        raise DispatchError("--consumer/--consumers requires at least one consumer")
    destination = _remote_destination(destinations)
    active_paths = paths or default_paths()
    changed_consumers: set[str] = set()

    # Keep the full read-modify-write transaction serialized so independent GWAY
    # processes cannot lose each other's bindings or race on EnvironmentFiles.
    with state_lock(active_paths):
        state = read_state(active_paths)
        bindings = state["bindings"]
        assert isinstance(bindings, dict)

        existing = bindings.get(destination)
        record = dict(existing) if isinstance(existing, dict) else {}
        current = _publisher_binding(record, destination)
        if current is not None and current.provider.casefold() != provider.casefold():
            current = None
        publisher_provider = _select_provider(
            provider,
            dispatch=dispatch,
            provider_resolver=provider_resolver,
        )
        publisher = publisher_provider.provision(
            destination=destination,
            consumer=selected[0],
            current=current,
        )
        if publisher.provider.casefold() != provider.casefold():
            raise DispatchError(
                f"log publisher provider {provider!r} returned binding for {publisher.provider!r}"
            )
        if publisher.destination != destination:
            raise DispatchError(
                "log publisher provider returned a binding for a different destination"
            )

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
                _, identities = consumer_identity(value, resolve_consumer)
                if identities & selected_identities:
                    removed.append(value)
                else:
                    remaining.append(value)
            for value in removed:
                detach_environment_files(value, owner="logs", paths=active_paths)
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
        combined, _ = canonical_consumers([*prior_values, *selected], resolve_consumer)
        combined_keys = {value.casefold() for value in combined}
        for previous in prior_values:
            if previous.casefold() not in combined_keys:
                detach_environment_files(previous, owner="logs", paths=active_paths)
                if _remove_environment(active_paths, previous):
                    changed_consumers.add(previous)

        record = {
            "provider": publisher.provider,
            "destination": destination,
            "publisher": publisher.to_record(),
            "consumers": list(combined),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        bindings[destination] = record
        write_state(active_paths, state)
        for consumer in combined:
            environment, changed = _write_environment(
                active_paths,
                consumer,
                publisher.environment,
            )
            attach_environment_files(
                consumer,
                owner="logs",
                environment_files=[environment],
                paths=active_paths,
            )
            if changed:
                changed_consumers.add(consumer)

    # Only a non-secret state-file path is exported for reload/exec continuity.
    # The bearer credential itself stays in private state and process-local HTTP
    # publisher context, so unrelated managed commands/subprocesses do not inherit it.
    os.environ[_STATE_PATH_ENV] = str(state_path(active_paths))
    activate_publisher_tokens((destination,), paths=active_paths)
    refreshed_services = (
        _refresh_running_consumer_services(sorted(changed_consumers), resolve_consumer)
        if changed_consumers
        else []
    )
    result: dict[str, object] = {
        "provider": publisher.provider,
        "destination": destination,
        "consumers": list(combined),
        "publisher": publisher.to_record(),
    }
    token_id = publisher.metadata.get("token_id")
    if isinstance(token_id, str):
        result["token_id"] = token_id
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
        state = read_state_path(state_path)
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
