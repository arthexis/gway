"""Lazy bootstrap and discovery for the uv executable used by recipe requirements."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

from .install.paths import data_root


UV_INSTALL_SH = "https://astral.sh/uv/install.sh"
UV_INSTALL_PS1 = "https://astral.sh/uv/install.ps1"


def managed_uv_root(*, system=False):
    """Return Gway's managed uv installation directory without creating it."""
    return (
        data_root(system=system).expanduser().resolve()
        / "tools"
        / "uv"
    )


def managed_uv_path(*, system=False):
    """Return the expected Gway-managed uv executable path."""
    name = "uv.exe" if os.name == "nt" else "uv"
    return managed_uv_root(system=system) / name


def find_uv(*, system=False):
    """Return the preferred usable uv executable, if one is already available."""
    managed = managed_uv_path(system=system)
    if managed.is_file():
        return managed.resolve()

    discovered = shutil.which("uv")
    if discovered:
        return Path(discovered).expanduser().resolve()
    return None


def _download_text(url):
    request = Request(url, headers={"User-Agent": "gway"})
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def _bootstrap_posix(target):
    script = _download_text(UV_INSTALL_SH)
    target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["UV_UNMANAGED_INSTALL"] = str(target)
    env["UV_NO_MODIFY_PATH"] = "1"
    subprocess.run(
        ["sh"],
        input=script,
        text=True,
        check=True,
        env=env,
    )


def _bootstrap_windows(target):
    target.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["UV_UNMANAGED_INSTALL"] = str(target)
    env["UV_NO_MODIFY_PATH"] = "1"
    command = (
        "irm '" + UV_INSTALL_PS1 + "' | iex"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "ByPass",
            "-Command",
            command,
        ],
        check=True,
        env=env,
    )


def bootstrap_uv(*, system=False):
    """Install uv into Gway-managed durable storage and return its executable."""
    target = managed_uv_root(system=system)
    if os.name == "nt":
        _bootstrap_windows(target)
    else:
        _bootstrap_posix(target)

    executable = managed_uv_path(system=system)
    if not executable.is_file():
        raise RuntimeError(
            f"uv installer completed without creating expected executable: {executable}"
        )
    return executable.resolve()


def ensure_uv(*, system=False):
    """Return a usable uv executable, bootstrapping one only when necessary."""
    existing = find_uv(system=system)
    if existing is not None:
        return existing
    return bootstrap_uv(system=system)
