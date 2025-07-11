# file: projects/games/evennia.py
"""Helpers to install and control an Evennia game environment."""

import os
import subprocess
import sys
from pathlib import Path
import urllib.request

from bottle import request

from gway import gw

DEFAULT_DIR = gw.resource("work", "games", "evennia")


def _run(cmd, *, cwd=None):
    """Execute a command list, logging and streaming output."""
    gw.info(f"Running: {' '.join(cmd)} (cwd={cwd})")
    process = subprocess.run(cmd, cwd=cwd, check=False)
    if process.returncode != 0:
        gw.error(f"Command {cmd[0]} exited with code {process.returncode}")
    return process.returncode


def install(*, target: str | Path = DEFAULT_DIR, version: str | None = None):
    """Install Evennia and initialize a game environment.

    Parameters:
        target: Path where the game environment lives. Defaults to
            ``work/games/evennia``.
        version: Optional version specifier passed to ``pip install``.
    """
    target = Path(target)
    os.makedirs(target, exist_ok=True)
    spec = "evennia" + (version or "")
    _run([sys.executable, "-m", "pip", "install", spec])
    if not (target / "server" / "settings.py").exists():
        _run([sys.executable, "-m", "evennia", "--init", "."], cwd=target)
    return str(target)


def manage(*args, path: str | Path = DEFAULT_DIR):
    """Run ``evennia`` management command in the environment."""
    path = Path(path)
    cmd = [sys.executable, "-m", "evennia", *args]
    return _run(cmd, cwd=path)


def start(*, path: str | Path = DEFAULT_DIR):
    """Start the Evennia server."""
    return manage("start", path=path)


def stop(*, path: str | Path = DEFAULT_DIR):
    """Stop the Evennia server."""
    return manage("stop", path=path)


def installed(path: str | Path = DEFAULT_DIR) -> bool:
    """Return True if an Evennia environment exists at ``path``."""
    path = Path(path)
    return (path / "server" / "settings.py").is_file()


def running(url: str = "http://localhost:4001/webclient") -> bool:
    """Return True if the Evennia web client responds at ``url``."""
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status < 500
    except Exception:
        return False


def view_evennia(*, action: str = None):
    """Simple HTML control for the Evennia server."""
    if action == "start":
        start()
        return "<p>Evennia server started.</p>"
    if action == "stop":
        stop()
        return "<p>Evennia server stopped.</p>"
    return (
        "<h1>Evennia</h1><p>Use ?action=start or ?action=stop to control the "
        "local server in work/games/evennia.</p>"
    )


def view_fantastic_client(*, url: str | None = None, action: str | None = None):
    """Display the Evennia web client or local setup helpers."""
    url = url or "http://localhost:4001/webclient"

    local = gw.web.server.is_local(request=request)

    if local and action:
        if action == "install":
            install()
            return "<p>Evennia installed. <a href=''>Refresh</a></p>"
        if action == "start":
            start()
            return "<p>Evennia server started. <a href=''>Refresh</a></p>"
        if action == "stop":
            stop()
            return "<p>Evennia server stopped. <a href=''>Refresh</a></p>"

    if running(url):
        return (
            "<h1>Fantastic Client</h1>"
            f"<iframe src='{url}' style='width:100%;height:600px;border:0;'></iframe>"
        )

    if not local:
        return "<p>Evennia server is not available.</p>"

    buttons = []
    if not installed():
        buttons.append(
            "<button type='submit' name='action' value='install'>Install Evennia</button>"
        )
    else:
        buttons.append(
            "<button type='submit' name='action' value='start'>Start Server</button>"
        )

    btn_html = "".join(buttons)
    return (
        "<h1>Fantastic Client</h1>"
        "<p>The local Evennia server is not running.</p>"
        "<form method='post'>" + btn_html + "</form>"
    )
