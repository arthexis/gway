"""Lazy bootstrap and discovery for the uv executable used by recipe requirements."""

from pathlib import Path
import os
import shutil
import subprocess
from urllib.request import Request, urlopen

from ..environment import environment_child
from ..install.paths import data_root


UV_INSTALL_SH = "https://astral.sh/uv/install.sh"
UV_INSTALL_PS1 = "https://astral.sh/uv/install.ps1"


def managed_uv_root(*, system=False, root=None):
    """Return Gway's managed uv installation directory without creating it."""
    base = data_root(system=system) if root is None else Path(root)
    return base.expanduser().resolve() / "tools" / "uv"


def managed_uv_path(*, system=False, root=None):
    """Return the expected Gway-managed uv executable path."""
    name = "uv.exe" if os.name == "nt" else "uv"
    return managed_uv_root(system=system, root=root) / name


def find_uv(*, system=False, root=None):
    """Return the preferred usable uv executable, if one is already available."""
    managed = managed_uv_path(system=system, root=root)
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
    env = environment_child(overrides={
        "UV_UNMANAGED_INSTALL": str(target),
        "UV_NO_MODIFY_PATH": "1",
    })
    subprocess.run(
        ["sh"],
        input=script,
        text=True,
        check=True,
        env=env,
    )


def _bootstrap_windows(target):
    target.mkdir(parents=True, exist_ok=True)
    env = environment_child(overrides={
        "UV_UNMANAGED_INSTALL": str(target),
        "UV_NO_MODIFY_PATH": "1",
    })
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


def bootstrap_uv(*, system=False, root=None):
    """Install uv into Gway-managed durable storage and return its executable."""
    target = managed_uv_root(system=system, root=root)
    if os.name == "nt":
        _bootstrap_windows(target)
    else:
        _bootstrap_posix(target)

    executable = managed_uv_path(system=system, root=root)
    if not executable.is_file():
        raise RuntimeError(
            f"uv installer completed without creating expected executable: {executable}"
        )
    return executable.resolve()


def ensure_uv(*, system=False, root=None):
    """Return a usable uv executable, bootstrapping one only when necessary."""
    existing = find_uv(system=system, root=root)
    if existing is not None:
        return existing
    return bootstrap_uv(system=system, root=root)
