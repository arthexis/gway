from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

DEFAULT_BACKEND = "file"
EVENT_FILE_ENV = "GWAY_EVENT_FILE"


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


def _default_event_file() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / "gway" / "events.jsonl"


def backend(name: str = DEFAULT_BACKEND, *, path: str | Path | None = None) -> EventBackend:
    if name == "file":
        return FileEventBackend(path)
    raise ValueError(f"unknown event backend: {name}")


def publish(
    event_type: str,
    /,
    *,
    backend_name: str = DEFAULT_BACKEND,
    path: str | Path | None = None,
    **data: Any,
) -> dict[str, Any]:
    event = Event.create(event_type, **data)
    return backend(backend_name, path=path).publish(event)


pub = publish

__all__ = [
    "DEFAULT_BACKEND",
    "EVENT_FILE_ENV",
    "Event",
    "EventBackend",
    "FileEventBackend",
    "backend",
    "pub",
    "publish",
]
