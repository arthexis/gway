"""Systemd unit materialization for Gway service launchables."""

from pathlib import Path
import shlex
import subprocess

from ...service.runtime import ProcessBackend
from .state import ServiceInstallRecord, ServiceInstallState


def unit_root(*, system=False, home=None):
    """Return the systemd unit directory for one installation scope."""
    if system:
        return Path("/etc/systemd/system")
    home = Path.home() if home is None else Path(home)
    return home / ".config" / "systemd" / "user"


def unit_name(project, service):
    """Return one safe .service unit filename."""
    raw = f"{project}-{service}"
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


def render(service, *, system=False):
    """Render one Gway service launchable as a systemd unit."""
    backend = ProcessBackend()
    command = backend._supervised_command(service)
    cwd = backend._cwd(service)
    lines = [
        "[Unit]",
        f"Description={service.description or service.project + '/' + service.name}",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={cwd}",
        "ExecStart=" + " ".join(shlex.quote(part) for part in command),
    ]
    lines.append("Restart=no")

    lines.extend(
        [
            "",
            "[Install]",
            "WantedBy=multi-user.target" if system else "WantedBy=default.target",
            "",
        ]
    )
    return "\n".join(lines)


def install_units(
    project,
    services,
    *,
    state_root,
    system=False,
    root=None,
):
    """Write and enable selected service units as additive upserts."""
    services = list(services)

    target_root = unit_root(system=system) if root is None else Path(root)
    target_root.mkdir(parents=True, exist_ok=True)
    state = ServiceInstallState(state_root)
    previous_all = state.get(project)
    previous = {
        record.service: record for record in previous_all if record.backend == "systemd"
    }
    selected = {service.name for service in services}

    previous_files = {}
    for record in previous.values():
        if record.service not in selected:
            continue
        path = target_root / record.backend_id
        try:
            previous_files[record.backend_id] = path.read_bytes()
        except FileNotFoundError:
            previous_files[record.backend_id] = None

    records = []
    try:
        for service in services:
            previous_record = previous.get(service.name)
            if previous_record is not None:
                filename = previous_record.backend_id
            else:
                filename = unit_name(project, service.name)
            path = target_root / filename
            path.write_text(
                render(service, system=system),
                encoding="utf-8",
            )
            records.append(
                ServiceInstallRecord(
                    project=project,
                    service=service.name,
                    backend_id=filename,
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
            _systemctl("enable", record.backend_id, system=system)
        retained = [record for record in previous_all if record.service not in selected]
        state.put(project, [*retained, *records])
        return records
    except Exception:
        for record in records:
            _systemctl("disable", record.backend_id, system=system, check=False)
            if record.backend_id not in previous_files:
                try:
                    (target_root / record.backend_id).unlink()
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
            _systemctl("enable", record.backend_id, system=record.system, check=False)
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
    state = ServiceInstallState(state_root)
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
        _systemctl(
            "disable", "--now", record.backend_id, system=record.system, check=False
        )
        try:
            (target_root / record.backend_id).unlink()
        except FileNotFoundError:
            pass
        _systemctl("daemon-reload", system=record.system, check=False)

    removed = {
        (record.backend, record.service, record.backend_id) for record in records
    }
    remaining = [
        record
        for record in all_records
        if (record.backend, record.service, record.backend_id) not in removed
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
            self.record.backend_id,
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
        _systemctl("start", self.record.backend_id, system=self.record.system)
        return self._status(service)

    def stop(self, service):
        """Stop one installed systemd service."""
        _systemctl(
            "stop", self.record.backend_id, system=self.record.system, check=False
        )
        return self._status(service)

    def restart(self, service):
        """Restart one installed systemd service."""
        _systemctl("restart", self.record.backend_id, system=self.record.system)
        return self._status(service)

    def status(self, service):
        """Return runtime status for one installed systemd service."""
        return self._status(service)


def runtime(*, record, **kwargs):
    """Return the systemd runtime adapter for one installed service."""
    return RuntimeBackend(record)
