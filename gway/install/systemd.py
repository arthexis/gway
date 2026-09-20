"""Systemd unit materialization for declared Gway services."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from ..service.runtime import ProcessBackend


@dataclass(frozen=True)
class UnitRecord:
    """Persisted mapping from one project service to a systemd unit."""

    project: str
    service: str
    unit: str
    system: bool = False
    backend: str = "systemd"
    restart: str | None = None
    attempts: int | None = None
    restart_sec: float | None = None
    command: tuple[str, ...] = ()


class UnitState:
    """Atomic JSON mapping for systemd units owned by installed projects."""

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
            UnitRecord(
                project=item["project"],
                service=item["service"],
                unit=item["unit"],
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
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    [asdict(record) for record in records],
                    stream,
                    indent=2,
                    sort_keys=True,
                )
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


def unit_root(*, system=False, home=None):
    """Return the systemd unit directory for one installation scope."""
    if system:
        return Path("/etc/systemd/system")
    home = Path.home() if home is None else Path(home)
    return home / ".config" / "systemd" / "user"


def unit_name(project, service, *, name=None):
    """Return one safe .service unit filename."""
    raw = name or f"{project}-{service}"
    raw = str(raw).strip()
    if raw.endswith(".service"):
        raw = raw[:-8]
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ValueError("systemd unit name must be one safe unit name")
    return f"{raw}.service"


def _systemctl(*args, system=False, check=True):
    command = ["systemctl"]
    if not system:
        command.append("--user")
    command.extend(args)
    return subprocess.run(
        command,
        check=check,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def render(service, *, unit, system=False):
    """Render one declared Gway service as a systemd unit."""
    backend = ProcessBackend()
    command = backend._supervised_command(service)
    cwd = backend._cwd(service)
    environment = backend._environment(service)
    declared_environment = {
        key: environment[key]
        for key in service.environment
    }

    lines = [
        "[Unit]",
        f"Description={service.description or service.project + '/' + service.name}",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={cwd}",
        "ExecStart=" + " ".join(shlex.quote(part) for part in command),
    ]
    for key, value in sorted(declared_environment.items()):
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'Environment="{key}={escaped}"')

    lines.append("Restart=no")

    lines.extend([
        "",
        "[Install]",
        "WantedBy=multi-user.target" if system else "WantedBy=default.target",
        "",
    ])
    return "\n".join(lines)


def install_units(
    project,
    services,
    *,
    state_root,
    system=False,
    name=None,
    root=None,
):
    """Write and enable selected service units, replacing prior mappings."""
    services = list(services)
    if name is not None and len(services) != 1:
        raise ValueError("--name requires exactly one selected service")

    target_root = unit_root(system=system) if root is None else Path(root)
    target_root.mkdir(parents=True, exist_ok=True)
    state = UnitState(state_root)
    previous_all = state.get(project)
    previous = {
        record.service: record
        for record in previous_all
        if record.backend == "systemd"
    }
    foreign = [
        record
        for record in previous_all
        if record.backend != "systemd"
    ]
    selected = {service.name for service in services}

    previous_files = {}
    for record in previous.values():
        path = target_root / record.unit
        try:
            previous_files[record.unit] = path.read_bytes()
        except FileNotFoundError:
            previous_files[record.unit] = None

    records = []
    try:
        # Remove units no longer selected by the converged install request.
        for service_name, record in previous.items():
            if service_name in selected:
                continue
            _systemctl("disable", record.unit, system=record.system, check=False)
            try:
                (target_root / record.unit).unlink()
            except FileNotFoundError:
                pass

        for service in services:
            previous_record = previous.get(service.name)
            if name is not None:
                filename = unit_name(project, service.name, name=name)
            elif previous_record is not None:
                filename = previous_record.unit
            else:
                filename = unit_name(project, service.name)
            path = target_root / filename
            path.write_text(
                render(service, unit=filename, system=system),
                encoding="utf-8",
            )
            records.append(
                UnitRecord(
                    project=project,
                    service=service.name,
                    unit=filename,
                    system=system,
                    backend="systemd",
                    restart=service.restart,
                    attempts=service.attempts,
                    restart_sec=service.restart_sec,
                    command=tuple(service.launchable.command),
                )
            )

        _systemctl("daemon-reload", system=system)
        for record in records:
            _systemctl("enable", record.unit, system=system)
        state.put(project, [*foreign, *records])
        return records
    except Exception:
        for record in records:
            _systemctl("disable", record.unit, system=system, check=False)
            if record.unit not in previous_files:
                try:
                    (target_root / record.unit).unlink()
                except FileNotFoundError:
                    pass
        for unit, content in previous_files.items():
            path = target_root / unit
            if content is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        state.put(project, previous_all)
        _systemctl("daemon-reload", system=system, check=False)
        for record in previous.values():
            _systemctl("enable", record.unit, system=record.system, check=False)
        raise


def uninstall_units(
    project,
    *,
    state_root,
    root=None,
    records=None,
    services=(),
    installations=None,
    process_state_root=None,
):
    """Disable and remove persisted systemd units owned by one project."""
    state = UnitState(state_root)
    all_records = state.get(project)
    records = (
        [record for record in all_records if record.backend == "systemd"]
        if records is None
        else list(records)
    )
    if not records:
        return []

    for record in records:
        target_root = unit_root(system=record.system) if root is None else Path(root)
        _systemctl("disable", "--now", record.unit, system=record.system, check=False)
        try:
            (target_root / record.unit).unlink()
        except FileNotFoundError:
            pass
        _systemctl("daemon-reload", system=record.system, check=False)

    removed = {(record.backend, record.service, record.unit) for record in records}
    remaining = [
        record
        for record in all_records
        if (record.backend, record.service, record.unit) not in removed
    ]
    state.put(project, remaining)
    return records



class RuntimeBackend:
    """Manage one installed service through systemd."""

    def __init__(self, record):
        self.record = record

    def _status(self, service):
        result = _systemctl(
            "is-active",
            self.record.unit,
            system=self.record.system,
            check=False,
        )
        running = getattr(result, "returncode", 1) == 0
        return {
            "project": service.project,
            "service": service.name,
            "running": running,
            "pid": None,
            "started_at": None,
            "stale": False,
        }

    def start(self, service):
        """Start one installed systemd service."""
        _systemctl("start", self.record.unit, system=self.record.system)
        return self._status(service)

    def stop(self, service):
        """Stop one installed systemd service."""
        _systemctl("stop", self.record.unit, system=self.record.system, check=False)
        return self._status(service)

    def restart(self, service):
        """Restart one installed systemd service."""
        _systemctl("restart", self.record.unit, system=self.record.system)
        return self._status(service)

    def status(self, service):
        """Return runtime status for one installed systemd service."""
        return self._status(service)


def runtime(*, record, **kwargs):
    """Return the systemd runtime adapter for one installed service."""
    return RuntimeBackend(record)
