"""Process-local backend for service lifecycle operations."""

import os
from pathlib import Path
import subprocess
import sys


class ProcessBackend:
    """Manage service processes owned by one Gateway instance."""

    def __init__(self):
        self._processes = {}

    @staticmethod
    def _python(service):
        candidate = service.root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
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

    def _key(self, service):
        return service.identity

    def start(self, service):
        """Start one process if it is not already running."""
        key = self._key(service)
        current = self._processes.get(key)
        if current is not None and current.poll() is None:
            return self.status(service)

        process = subprocess.Popen(
            self._command(service),
            cwd=self._cwd(service),
            env=self._environment(service),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[key] = process
        return self.status(service)

    def stop(self, service):
        """Stop one process owned by this backend."""
        key = self._key(service)
        process = self._processes.get(key)
        if process is None or process.poll() is not None:
            self._processes.pop(key, None)
            return {
                "project": service.project,
                "service": service.name,
                "running": False,
                "pid": None,
            }

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._processes.pop(key, None)
        return {
            "project": service.project,
            "service": service.name,
            "running": False,
            "pid": None,
        }

    def restart(self, service):
        """Stop and start one process owned by this backend."""
        self.stop(service)
        return self.start(service)

    def status(self, service):
        """Return current process-local status for one service."""
        process = self._processes.get(self._key(service))
        running = process is not None and process.poll() is None
        return {
            "project": service.project,
            "service": service.name,
            "running": running,
            "pid": process.pid if running else None,
        }
