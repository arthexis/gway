"""Platform-safe cache path selection."""

import os
from pathlib import Path
import sys


def default_root(*, environ=None, platform=None, home=None):
    """Return GWAY's per-user cache root without creating it."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    override = environ.get("GWAY_CACHE_DIR")
    if override:
        return Path(override).expanduser()

    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "gway" / "cache"
        return home / "AppData" / "Local" / "gway" / "cache"

    if platform == "darwin":
        return home / "Library" / "Caches" / "gway"

    base = environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base).expanduser() / "gway"
    return home / ".cache" / "gway"
