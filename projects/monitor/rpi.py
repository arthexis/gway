# file: projects/monitor/rpi.py
"""Raspberry Pi utilities."""

import subprocess
import os
import html
import threading
from gway import gw


def ru(target_device: str, *, bs: str = "4M", sync: bool = True) -> str:
    """Clone the running Raspberry Pi image to ``target_device`` using ``dd``.

    Parameters
    ----------
    target_device: str
        Path to the destination block device (e.g. ``/dev/sda``).
    bs: str
        Block size for ``dd`` (default ``4M``).
    sync: bool
        If ``True``, use ``conv=fsync`` to sync writes.

    Returns
    -------
    str
        Standard output from ``dd`` when successful.
    """
    cmd = [
        "sudo",
        "dd",
        "if=/dev/mmcblk0",
        f"of={target_device}",
        f"bs={bs}",
        "status=progress",
    ]
    if sync:
        cmd.append("conv=fsync")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"dd failed: {result.stderr.strip()}")
    return result.stdout.strip() or "Clone completed."


# alias
clone_sd = ru


_CLONE_STATE = {
    "running": False,
    "progress": 0.0,
    "status": "",
    "target": "",
}


def _run_clone(target: str):
    """Background thread wrapper around :func:`ru`.

    Updates the global ``_CLONE_STATE`` with progress and final status.
    """
    try:
        ru(target)
        _CLONE_STATE.update(progress=100.0, status="Clone completed.")
    except Exception as exc:  # pragma: no cover - error path
        _CLONE_STATE.update(status=f"Error: {exc}")
    finally:
        _CLONE_STATE["running"] = False


def _list_devices() -> list[str]:
    """Return list of potential target devices under ``/dev``."""
    import re

    try:
        devs = os.listdir("/dev")
    except Exception:  # pragma: no cover - inaccessible /dev
        return []
    pattern = re.compile(r"^(sd[a-z]|mmcblk\d+)$")
    return [f"/dev/{d}" for d in devs if pattern.match(d)]


def render_clone_progress():

    prog = _CLONE_STATE.get("progress", 0.0)
    status = _CLONE_STATE.get("status", "")
    bar = (
        f"<div class='gw-progress'><div class='gw-progress-bar' "
        f"style='width:{prog:.1f}%'>{prog:.1f}%</div></div>"
    )
    msg = html.escape(status) if status else "Running..." if _CLONE_STATE["running"] else ""
    if msg:
        return bar + f"<p>{msg}</p>"
    return bar


def render_rpi(target: str | None = None) -> str:
    """Return HTML fragment for the Pi clone interface."""
    if target and not _CLONE_STATE["running"]:
        _CLONE_STATE.update(running=True, progress=0.0, status="", target=target)
        threading.Thread(target=_run_clone, args=(target,), daemon=True).start()

    devices = _list_devices()
    options = ""
    for d in devices:
        sel = " selected" if d == target else ""
        options += f'<option value="{d}"{sel}>{d}</option>'
    form = (
        "<form method='post'>"
        f"<select name='target'>{options}</select>"
        "<button type='submit'>Clone</button>"
        "</form>"
    )
    progress = (
        "<div id='clone-progress' gw-render='clone_progress' "
        "gw-refresh='1' gw-on-load></div>"
    )
    return "".join(["<h2>Pi Remote Clone</h2>", form, progress])


def monitor_rpi():
    """Simple monitor that exposes clone state."""
    gw.monitor.set_states("rpi", _CLONE_STATE.copy())
    return _CLONE_STATE.copy()


def view_pi_remote(*, target: str = None):
    """Web view to clone the running Pi to another card.

    Providing ``target`` will start the cloning process. Otherwise a form
    with available devices is shown. The progress bar refreshes automatically
    using ``render_clone_progress``.
    """
    html = "<h1>Pi Remote Clone</h1>" + render_rpi(target)
    return gw.web.app.render_template(
        title="Pi Remote Clone",
        content=html,
        css_files=["/static/tabs.css"],
        js_files=["/static/render.js"],
    )
