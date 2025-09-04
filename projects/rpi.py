# file: projects/rpi.py
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


