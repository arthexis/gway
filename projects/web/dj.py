# file: projects/web/dj.py
"""Helpers to control a Django project defined via ``DJANGO_SETTINGS_MODULE``."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

from gway import gw


def _run(cmd, *, cwd=None):
    """Execute a command list, logging and streaming output."""
    gw.info(f"Running: {' '.join(cmd)} (cwd={cwd})")
    process = subprocess.run(cmd, cwd=cwd, check=False)
    if process.returncode != 0:
        gw.error(f"Command {cmd[0]} exited with code {process.returncode}")
    return process.returncode


def _project_dir_from_env() -> Path | None:
    """Return the Django project directory from ``DJANGO_SETTINGS_MODULE``.

    The variable should point to ``<project>.settings``.  This function
    imports that module and returns the directory containing ``manage.py``.
    Returns ``None`` if the environment variable is missing or invalid.
    """
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
    if not settings_module:
        return None
    try:
        module = importlib.import_module(settings_module)
    except Exception as exc:  # pragma: no cover - import error messaging
        gw.error(f"Cannot import {settings_module}: {exc}")
        return None
    return Path(module.__file__).resolve().parents[1]


def manage(*args, path: str | Path | None = None):
    """Run ``manage.py`` command in the configured Django project."""
    if path is None:
        path = _project_dir_from_env()
    if not path:
        gw.error("Django project not found. Set DJANGO_SETTINGS_MODULE")
        return 1
    path = Path(path)
    if not (path / "manage.py").exists():
        gw.error(f"manage.py not found in {path}")
        return 1
    cmd = [sys.executable, "manage.py", *args]
    return _run(cmd, cwd=path)


def start(*, path: str | Path | None = None, addrport: str = "127.0.0.1:8000"):
    """Start the Django development server."""
    return manage("runserver", addrport, path=path)


def stop(*, pattern: str = "manage.py", signal: str = "TERM"):
    """Stop the Django development server using pkill if available."""
    return _run(["pkill", f"-{signal}", "-f", pattern])

def view_dj(*, action: str = None, host: str = "127.0.0.1", port: int = 8000):
    """Control an existing Django server."""
    project_dir = _project_dir_from_env()
    manage_py = project_dir / "manage.py" if project_dir else None

    if action == "start":
        if not manage_py or not manage_py.exists():
            return "<p>Django not configured. Set DJANGO_SETTINGS_MODULE.</p>"
        start(path=project_dir, addrport=f"{host}:{port}")
        url = f"http://{host}:{port}/"
        return f"<p>Django server started at <a href='{url}'>{url}</a></p>"

    if action == "stop":
        stop()
        return "<p>Django server stopped.</p>"

    if not manage_py or not manage_py.exists():
        return "<p>Django not configured. Set DJANGO_SETTINGS_MODULE.</p>"

    return (
        "<h1>Django</h1><p>Use ?action=start or ?action=stop to control the "
        "server defined by DJANGO_SETTINGS_MODULE.</p>"
    )
