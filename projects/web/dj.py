# file: projects/web/dj.py
"""Helpers to install and control an embedded Django project."""

import os
import subprocess
import sys
from pathlib import Path

from gway import gw

DEFAULT_DIR = gw.resource("work", "web", "dj")


def _run(cmd, *, cwd=None):
    """Execute a command list, logging and streaming output."""
    gw.info(f"Running: {' '.join(cmd)} (cwd={cwd})")
    process = subprocess.run(cmd, cwd=cwd, check=False)
    if process.returncode != 0:
        gw.error(f"Command {cmd[0]} exited with code {process.returncode}")
    return process.returncode


def install(*, target: str | Path = DEFAULT_DIR, version: str | None = None, project: str = "config"):
    """Install Django and start a project in the target directory.

    Parameters:
        target: Path where the project lives. Defaults to ``work/web/dj``.
        version: Optional version specifier passed to ``pip install``.
        project: Name for the Django project folder (default ``config``).
    """
    target = Path(target)
    os.makedirs(target, exist_ok=True)
    spec = "django" + (version or "")
    _run([sys.executable, "-m", "pip", "install", spec])
    if not (target / "manage.py").exists():
        _run(["django-admin", "startproject", project, "."], cwd=target)
    return str(target)


def manage(*args, path: str | Path = DEFAULT_DIR):
    """Run ``manage.py`` command in the environment."""
    path = Path(path)
    cmd = [sys.executable, "manage.py", *args]
    return _run(cmd, cwd=path)


def start(*, path: str | Path = DEFAULT_DIR, addrport: str = "127.0.0.1:8000"):
    """Start the Django development server."""
    return manage("runserver", addrport, path=path)


def stop(*, pattern: str = "manage.py", signal: str = "TERM"):
    """Stop the Django development server using pkill if available."""
    return _run(["pkill", f"-{signal}", "-f", pattern])

def view_dj(*, action: str = None, host: str = "127.0.0.1", port: int = 8000):
    """Install and control the embedded Django server."""
    project_dir = Path(DEFAULT_DIR)
    manage_py = project_dir / "manage.py"

    if action == "install":
        install(target=project_dir)
        return "<p>Django installed.</p>"

    if action == "start":
        if not manage_py.exists():
            install(target=project_dir)
        start(path=project_dir, addrport=f"{host}:{port}")
        url = f"http://{host}:{port}/"
        return f"<p>Django server started at <a href='{url}'>{url}</a></p>"

    if action == "stop":
        stop()
        return "<p>Django server stopped.</p>"

    if not manage_py.exists():
        return (
            "<p>Django not installed. Use ?action=install to install it</p>"
        )

    return (
        "<h1>Django</h1><p>Use ?action=start or ?action=stop to control the "
        "local server in work/web/dj.</p>"
    )
