"""Durable subprocess backend for service lifecycle operations."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .state import ServiceState, new_record, record_matches


class ProcessBackend:
    """Manage project-owned service processes across Gateway instances."""

    def __init__(self, *, state_root=None, installations=None):
        self.installations = installations or {}
        self._processes = {}
        self.state_root = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else None
        )

    @staticmethod
    def _python(service):
        candidate = service.root / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        if candidate.is_file():
            return str(candidate)
        return sys.executable

    @classmethod
    def _expand(cls, service, value):
        return (
            str(value)
            .replace("{project}", str(service.root))
            .replace("{python}", cls._python(service))
        )

    @classmethod
    def _command(cls, service):
        return [cls._expand(service, part) for part in service.command]

    @classmethod
    def _cwd(cls, service):
        value = service.working_directory or "{project}"
        return Path(cls._expand(service, value)).expanduser().resolve()

    @classmethod
    def _environment(cls, service):
        environment = os.environ.copy()
        environment.update(
            {
                name: cls._expand(service, value)
                for name, value in service.environment.items()
            }
        )
        return environment

    def _state(self, service):
        root = self.state_root or (service.root.parent.parent / "services")
        return ServiceState(root)

    def _project_fingerprint(self, service):
        installation = self.installations.get(service.project)
        return getattr(installation, "fingerprint", None)

    def _record(self, service):
        return self._state(service).get(service.project, service.name)

    @staticmethod
    def _wait_gone(pid, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if hasattr(os, "waitpid"):
                try:
                    waited, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    waited = 0
                if waited == pid:
                    return True
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except OSError:
                return True
            time.sleep(0.05)
        return False

    def start(self, service):
        """Start one service unless a matching owned process is already live."""
        state = self._state(service)
        current = state.get(service.project, service.name)
        if current is not None:
            if record_matches(current):
                return self.status(service)
            state.remove(service.project, service.name)

        command = self._command(service)
        cwd = self._cwd(service)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=self._environment(service),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        self._processes[service.identity] = process
        record = new_record(
            service,
            process.pid,
            command,
            cwd,
            project_fingerprint=self._project_fingerprint(service),
        )
        state.put(record)
        return self.status(service)

    def stop(self, service):
        """Stop one matching process owned by durable Gway service state."""
        state = self._state(service)
        local = self._processes.get(service.identity)
        if local is not None:
            returncode = local.poll()
            if returncode is not None:
                self._processes.pop(service.identity, None)
                state.remove(service.project, service.name)
                return self._stopped(service)

        record = state.get(service.project, service.name)
        if record is None:
            return self._stopped(service)

        if not record_matches(record):
            state.remove(service.project, service.name)
            return self._stopped(service)

        local = self._processes.get(service.identity)
        if local is not None and local.poll() is None:
            local.terminate()
            try:
                local.wait(timeout=5)
            except subprocess.TimeoutExpired:
                local.kill()
                local.wait(timeout=5)
        else:
            try:
                os.kill(record.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        if local is None and not self._wait_gone(record.pid):
            try:
                os.kill(record.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._wait_gone(record.pid)

        self._processes.pop(service.identity, None)
        state.remove(service.project, service.name)
        return self._stopped(service)

    def restart(self, service):
        """Stop any matching owned process and start a replacement."""
        self.stop(service)
        return self.start(service)

    def status(self, service):
        """Return durable runtime status for one discovered service."""
        state = self._state(service)
        record = state.get(service.project, service.name)
        if record is None:
            return self._stopped(service)

        if not record_matches(record):
            state.remove(service.project, service.name)
            return self._stopped(service)

        current_fingerprint = self._project_fingerprint(service)
        stale = (
            record.project_fingerprint is not None
            and current_fingerprint is not None
            and record.project_fingerprint != current_fingerprint
        )
        return {
            "project": service.project,
            "service": service.name,
            "running": True,
            "pid": record.pid,
            "started_at": record.started_at,
            "stale": stale,
        }

    @staticmethod
    def _stopped(service):
        return {
            "project": service.project,
            "service": service.name,
            "running": False,
            "pid": None,
            "started_at": None,
            "stale": False,
        }
