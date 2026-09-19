"""Durable installation data paths."""

from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class InstallPaths:
    """One installation scope's durable locations."""

    root: Path
    projects: Path
    stashes: Path
    state: Path
    scope: str


def data_root(*, system=False, environ=None, platform=None, home=None):
    """Return GWAY's durable data root without creating it."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    override_name = "GWAY_SYSTEM_DATA_DIR" if system else "GWAY_DATA_DIR"
    override = environ.get(override_name)
    if override:
        return Path(override).expanduser()

    if system:
        if platform.startswith("win"):
            base = environ.get("PROGRAMDATA")
            return Path(base) / "gway" if base else Path("C:/ProgramData/gway")
        if platform == "darwin":
            return Path("/Library/Application Support/gway")
        return Path("/var/lib/gway")

    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "gway"
        return home / "AppData" / "Local" / "gway"

    if platform == "darwin":
        return home / "Library" / "Application Support" / "gway"

    base = environ.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser() / "gway"
    return home / ".local" / "share" / "gway"


def install_paths(*, system=False, root=None, **kwargs):
    """Return all durable paths for one installation scope."""
    selected = (
        data_root(system=system, **kwargs)
        if root is None
        else Path(root).expanduser()
    ).resolve()
    return InstallPaths(
        root=selected,
        projects=selected / "projects",
        stashes=selected / "stashes",
        state=selected / "state.sqlite",
        scope="system" if system else "user",
    )
