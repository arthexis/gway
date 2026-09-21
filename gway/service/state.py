"""Durable ownership state for managed service processes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
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
    project_fingerprint: str | None = None

    @property
    def identity(self):
        return self.project, self.service


def _procfs_process_token(pid):
    """Return Linux procfs start-time identity when available."""
    stat = Path(f"/proc/{int(pid)}/stat")
    try:
        text = stat.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None

    # Linux procfs field 22 is process start time. The command field can
    # contain spaces/parentheses, so split only after its final ')'.
    try:
        tail = text[text.rindex(")") + 2 :].split()
        if tail[0] == "Z":
            return None
        return f"procfs:{tail[19]}"
    except (ValueError, IndexError):
        return None


def _windows_process_token(pid):
    """Return Windows process creation time without third-party dependencies."""
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not process:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            ok = ctypes.windll.kernel32.GetProcessTimes(
                process,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not ok:
                return None
            value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return f"windows:{value}"
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    except (AttributeError, OSError, ValueError):
        return None


def _ps_process_token(pid):
    """Return portable POSIX process start identity when procfs is unavailable."""
    if os.name == "nt":
        return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(int(pid))],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired, ValueError):
        return None
    started = result.stdout.strip()
    if result.returncode != 0 or not started:
        return None
    return f"ps:{started}"


def process_token(pid):
    """Return a portable process start-identity token when available."""
    return (
        _procfs_process_token(pid)
        or _windows_process_token(pid)
        or _ps_process_token(pid)
    )


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


def record_matches(record, process=None):
    """Return whether a live process still matches one ownership record."""
    if process is not None:
        return process.pid == record.pid and process.poll() is None
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
            project_fingerprint=data.get("project_fingerprint"),
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


def new_record(
    service,
    pid,
    command,
    cwd,
    *,
    project_fingerprint=None,
):
    """Create one ownership record for a newly spawned process."""
    return ProcessRecord(
        project=service.project,
        service=service.name,
        pid=int(pid),
        process_token=process_token(pid),
        command=tuple(command),
        cwd=str(cwd),
        started_at=datetime.now(timezone.utc).isoformat(),
        project_fingerprint=project_fingerprint,
    )
