"""Durable ownership state for managed service processes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class ProcessRecord:
    """Durable ownership record for one started service process."""

    project: str
    service: str
    pid: int
    process_token: str | None
    command: tuple[str, ...]
    cwd: str
    started_at: str

    @property
    def identity(self):
        return self.project, self.service


def process_token(pid):
    """Return a kernel process-identity token when the platform exposes one."""
    stat = Path(f"/proc/{int(pid)}/stat")
    try:
        text = stat.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None

    # Linux procfs field 22 is process start time. The command field can
    # contain spaces/parentheses, so split only after its final ')'.
    try:
        tail = text[text.rindex(")") + 2 :].split()
        return tail[19]
    except (ValueError, IndexError):
        return None


def pid_exists(pid):
    """Return whether a process ID currently exists."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def record_matches(record):
    """Return whether a live process still matches one ownership record."""
    if not pid_exists(record.pid):
        return False
    if record.process_token is None:
        return False
    return process_token(record.pid) == record.process_token


class ServiceState:
    """Atomic JSON ownership state below one installation data root."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def path(self, project, service):
        return self.root / project / f"{service}.json"

    def get(self, project, service):
        path = self.path(project, service)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return ProcessRecord(
            project=data["project"],
            service=data["service"],
            pid=int(data["pid"]),
            process_token=data.get("process_token"),
            command=tuple(data.get("command", ())),
            cwd=data["cwd"],
            started_at=data["started_at"],
        )

    def put(self, record):
        path = self.path(record.project, record.service)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        payload["command"] = list(record.command)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{record.service}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temp = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return record

    def remove(self, project, service):
        path = self.path(project, service)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True


def new_record(service, pid, command, cwd):
    """Create one ownership record for a newly spawned process."""
    return ProcessRecord(
        project=service.project,
        service=service.name,
        pid=int(pid),
        process_token=process_token(pid),
        command=tuple(command),
        cwd=str(cwd),
        started_at=datetime.now(timezone.utc).isoformat(),
    )
