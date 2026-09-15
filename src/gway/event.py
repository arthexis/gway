from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

DEFAULT_BACKEND = "file"
EVENT_FILE_ENV = "GWAY_EVENT_FILE"
EVENT_PROVIDER_ENV = "GWAY_EVENT_PROVIDER"


@dataclass(frozen=True, slots=True)
class Event:
    type: str
    data: dict[str, Any]
    time: str

    @classmethod
    def create(cls, event_type: str, **data: Any) -> Event:
        return cls(
            type=event_type,
            data=data,
            time=datetime.now(timezone.utc).isoformat(),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBackend(Protocol):
    def publish(self, event: Event) -> dict[str, Any]: ...


class FileEventBackend:
    name = "file"

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get(EVENT_FILE_ENV)
        self.path = Path(configured) if configured else _default_event_file()

    def publish(self, event: Event) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = event.as_dict()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, separators=(",", ":"), default=str))
            stream.write("\n")
        return payload


class CallableEventBackend:
    """Publish events through an ordinary Gway project callable."""

    name = "callable"

    def __init__(
        self,
        provider: str,
        dispatch: Callable[[str, list[str]], object],
    ) -> None:
        project, separator, command = provider.partition(":")
        project = project.strip()
        command = command.strip() if separator else "event"
        if not project or not command:
            raise ValueError("event provider must use PROJECT or PROJECT:COMMAND syntax")
        self.project = project
        self.command = command
        self.dispatch = dispatch

    def publish(self, event: Event) -> dict[str, Any]:
        result = self.dispatch(
            self.project,
            [
                self.command,
                "pub",
                event.type,
                "--data",
                json.dumps(event.data, separators=(",", ":"), default=str),
            ],
        )
        if isinstance(result, str):
            try:
                decoded = json.loads(result)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                return decoded
        if isinstance(result, dict):
            return result
        return event.as_dict()


def _default_event_file() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / "gway" / "events.jsonl"


def backend(
    name: str = DEFAULT_BACKEND,
    *,
    path: str | Path | None = None,
    provider: str | None = None,
    dispatch: Callable[[str, list[str]], object] | None = None,
) -> EventBackend:
    if name == "file":
        return FileEventBackend(path)
    if name == "callable":
        if provider is None:
            raise ValueError("callable event backend requires a provider")
        if dispatch is None:
            raise ValueError("callable event backend requires Gway dispatch")
        return CallableEventBackend(provider, dispatch)
    raise ValueError(f"unknown event backend: {name}")


def publish(
    event_type: str,
    /,
    *,
    backend_name: str = DEFAULT_BACKEND,
    path: str | Path | None = None,
    provider: str | None = None,
    dispatch: Callable[[str, list[str]], object] | None = None,
    **data: Any,
) -> dict[str, Any]:
    event = Event.create(event_type, **data)
    return backend(
        backend_name,
        path=path,
        provider=provider,
        dispatch=dispatch,
    ).publish(event)


pub = publish

__all__ = [
    "CallableEventBackend",
    "DEFAULT_BACKEND",
    "EVENT_FILE_ENV",
    "EVENT_PROVIDER_ENV",
    "Event",
    "EventBackend",
    "FileEventBackend",
    "backend",
    "pub",
    "publish",
]
