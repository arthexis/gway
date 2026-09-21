"""Systemd unit materialization for Gway service launchables."""

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess

from ... import log as gway_log
from ...service.runtime import ProcessBackend
from .state import ServiceInstallRecord, ServiceInstallState


SYSTEMCTL_TIMEOUT = 40.0


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


class _SystemdOperationError(RuntimeError):
    """Structured failure for one concrete systemd operation."""

    def __init__(
        self,
        operation,
        message,
        *,
        returncode=None,
        timeout=None,
        stdout="",
        stderr="",
    ):
        super().__init__(message)
        self.operation = operation
        self.action = operation.action
        self.unit = operation.unit
        self.system = operation.system
        self.returncode = returncode
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr


def _diagnostic_text(value, *, limit=4000):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


@dataclass(frozen=True)
class _SystemdOperation:
    """Structured identity for one concrete systemctl subprocess."""

    action: str
    unit: str | None
    arguments: tuple[str, ...]
    system: bool = False

    @property
    def command(self):
        command = ["systemctl"]
        if not self.system:
            command.append("--user")
        command.extend((self.action, *self.arguments))
        return command

    @classmethod
    def from_call(cls, args, *, system=False):
        args = tuple(args)
        if not args:
            raise ValueError("systemctl operation requires an action")
        action = args[0]
        arguments = args[1:]
        unit = next(
            (
                value
                for value in reversed(arguments)
                if isinstance(value, str) and not value.startswith("-")
            ),
            None,
        )
        return cls(
            action=action,
            unit=unit,
            arguments=arguments,
            system=system,
        )


def _run_systemctl_operation(
    operation,
    *,
    check=True,
    timeout=SYSTEMCTL_TIMEOUT,
):
    scope = "system" if operation.system else "user"
    target = operation.unit or "(global)"
    gway_log.info(
        "systemd %s %s [%s]: starting",
        operation.action,
        target,
        scope,
    )
    try:
        result = subprocess.run(
            operation.command,
            check=check,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _diagnostic_text(exc.stdout)
        stderr = _diagnostic_text(exc.stderr)
        gway_log.error(
            "systemd %s %s [%s]: timed out after %ss",
            operation.action,
            target,
            scope,
            exc.timeout,
        )
        message = (
            f"systemd operation timed out after {exc.timeout}s: "
            f"action={operation.action} target={target} scope={scope}"
        )
        if stderr:
            message += f": {stderr}"
        elif stdout:
            message += f": {stdout}"
        raise _SystemdOperationError(
            operation,
            message,
            timeout=exc.timeout,
            stdout=stdout,
            stderr=stderr,
        ) from exc
    except subprocess.CalledProcessError as exc:
        stdout = _diagnostic_text(exc.stdout)
        stderr = _diagnostic_text(exc.stderr)
        gway_log.error(
            "systemd %s %s [%s]: failed with exit %s",
            operation.action,
            target,
            scope,
            exc.returncode,
        )
        message = (
            "systemd operation failed: "
            f"action={operation.action} target={target} "
            f"scope={scope} exit={exc.returncode}"
        )
        if stderr:
            message += f": {stderr}"
        elif stdout:
            message += f": {stdout}"
        raise _SystemdOperationError(
            operation,
            message,
            returncode=exc.returncode,
            stdout=stdout,
            stderr=stderr,
        ) from exc
    gway_log.info(
        "systemd %s %s [%s]: complete",
        operation.action,
        target,
        scope,
    )
    return result


def _systemctl(*args, system=False, check=True, timeout=SYSTEMCTL_TIMEOUT):
    operation = _SystemdOperation.from_call(args, system=system)
    return _run_systemctl_operation(operation, check=check, timeout=timeout)


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


def _rollback_install_units(
    project,
    *,
    records,
    previous,
    previous_all,
    previous_files,
    state,
    target_root,
    system,
    timeout,
):
    """Best-effort rollback for a failed systemd unit installation."""
    for record in records:
        try:
            _systemctl(
                "disable",
                record.backend_id,
                system=system,
                check=False,
                timeout=timeout,
            )
        except Exception:
            pass
        if record.backend_id not in previous_files:
            try:
                (target_root / record.backend_id).unlink()
            except Exception:
                pass

    for unit, content in previous_files.items():
        path = target_root / unit
        try:
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        except Exception:
            pass

    try:
        state.put(project, previous_all)
    except Exception:
        pass

    try:
        _systemctl("daemon-reload", system=system, check=False, timeout=timeout)
    except Exception:
        pass

    for record in previous.values():
        try:
            _systemctl(
                "enable",
                record.backend_id,
                system=record.system,
                check=False,
                timeout=timeout,
            )
        except Exception:
            pass


def install_units(
    project,
    services,
    *,
    state_root,
    system=False,
    root=None,
    timeout=SYSTEMCTL_TIMEOUT,
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

        _systemctl("daemon-reload", system=system, timeout=timeout)
        for record in records:
            _systemctl("enable", record.backend_id, system=system, timeout=timeout)
        retained = [record for record in previous_all if record.service not in selected]
        state.put(project, [*retained, *records])
        return records
    except Exception:
        _rollback_install_units(
            project,
            records=records,
            previous=previous,
            previous_all=previous_all,
            previous_files=previous_files,
            state=state,
            target_root=target_root,
            system=system,
            timeout=timeout,
        )
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
    timeout=SYSTEMCTL_TIMEOUT,
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
            "disable",
            "--now",
            record.backend_id,
            system=record.system,
            check=False,
            timeout=timeout,
        )
        try:
            (target_root / record.backend_id).unlink()
        except FileNotFoundError:
            pass
        _systemctl(
            "daemon-reload",
            system=record.system,
            check=False,
            timeout=timeout,
        )

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

    def __init__(self, record, *, timeout=SYSTEMCTL_TIMEOUT):
        self.record = record
        self.timeout = timeout

    def _status(self, service):
        result = _systemctl(
            "is-active",
            self.record.backend_id,
            system=self.record.system,
            check=False,
            timeout=self.timeout,
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
        _systemctl(
            "start",
            self.record.backend_id,
            system=self.record.system,
            timeout=self.timeout,
        )
        return self._status(service)

    def stop(self, service):
        """Stop one installed systemd service."""
        _systemctl(
            "stop",
            self.record.backend_id,
            system=self.record.system,
            check=False,
            timeout=self.timeout,
        )
        return self._status(service)

    def restart(self, service):
        """Restart one installed systemd service."""
        _systemctl(
            "restart",
            self.record.backend_id,
            system=self.record.system,
            timeout=self.timeout,
        )
        return self._status(service)

    def status(self, service):
        """Return runtime status for one installed systemd service."""
        return self._status(service)


def runtime(*, record, timeout=SYSTEMCTL_TIMEOUT, **kwargs):
    """Return the systemd runtime adapter for one installed service."""
    return RuntimeBackend(record, timeout=timeout)
