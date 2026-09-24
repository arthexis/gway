"""Durable installation data paths."""

from dataclasses import dataclass
from pathlib import Path
import sys

from ..environment import process_environment


@dataclass(frozen=True)
class InstallPaths:
    """One installation scope's durable locations."""

    root: Path
    projects: Path
    stashes: Path
    launchers: Path
    bin: Path
    state: Path
    scope: str


def data_root(*, system=False, data_dir=None, environ=None, platform=None, home=None):
    """Return GWAY's platform data root or one explicit semantic override."""
    environ = process_environment if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    if data_dir is not None:
        return Path(data_dir).expanduser()

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


def bin_root(*, system=False, bin_dir=None, environ=None, platform=None, home=None):
    """Return the platform activation bin directory or one explicit override."""
    environ = process_environment if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    if bin_dir is not None:
        return Path(bin_dir).expanduser()

    if platform.startswith("win"):
        base = environ.get("PROGRAMDATA" if system else "LOCALAPPDATA")
        if base:
            return Path(base) / "gway" / "bin"
        if system:
            return Path("C:/ProgramData/gway/bin")
        return home / "AppData" / "Local" / "gway" / "bin"

    if system:
        return Path("/usr/local/bin")
    return home / ".local" / "bin"


def install_paths(
    *,
    system=False,
    root=None,
    data_dir=None,
    bin_dir=None,
    **kwargs,
):
    """Return all durable paths from platform defaults or explicit values."""
    selected = (
        data_root(system=system, data_dir=data_dir, **kwargs)
        if root is None
        else Path(root).expanduser()
    ).resolve()
    selected_bin = bin_root(system=system, bin_dir=bin_dir, **kwargs).resolve()
    return InstallPaths(
        root=selected,
        projects=selected / "projects",
        stashes=selected / "stashes",
        launchers=selected / "launchers",
        bin=selected_bin,
        state=selected / "state.sqlite",
        scope="system" if system else "user",
    )
