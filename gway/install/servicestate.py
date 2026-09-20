"""Persistent backend-neutral service installation state."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class ServiceInstallRecord:
    """Persisted mapping from one service identity to a backend artifact."""

    project: str
    service: str
    backend_id: str
    system: bool = False
    backend: str = "systemd"
    restart: str | None = None
    attempts: int | None = None
    restart_sec: float | None = None
    command: tuple[str, ...] = ()


class ServiceInstallState:
    """Atomic service-installation records below one data root."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def path(self, project):
        return self.root / f"{project}.json"

    def get(self, project):
        path = self.path(project)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        return [
            ServiceInstallRecord(
                project=item["project"],
                service=item["service"],
                backend_id=item["backend_id"],
                system=bool(item.get("system", False)),
                backend=item.get("backend", "systemd"),
                restart=item.get("restart"),
                attempts=item.get("attempts"),
                restart_sec=item.get("restart_sec"),
                command=tuple(item.get("command", ())),
            )
            for item in data
        ]

    def put(self, project, records):
        path = self.path(project)
        records = list(records)
        if not records:
            self.remove(project)
            return records

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{project}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temp = Path(temporary)
        try:
            payload = []
            for record in records:
                item = asdict(record)
                item["command"] = list(record.command)
                payload.append(item)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return records

    def remove(self, project):
        try:
            self.path(project).unlink()
        except FileNotFoundError:
            return False
        return True
