"""Platform-safe cache path selection."""

import os
from pathlib import Path
import sys


def default_root():
    """Return GWAY's per-user cache root without creating it."""
    override = os.environ.get("GWAY_CACHE_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "gway" / "cache"
        return Path.home() / "AppData" / "Local" / "gway" / "cache"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "gway"

    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base).expanduser() / "gway"
    return Path.home() / ".cache" / "gway"
