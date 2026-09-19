"""Built-in GWAY operations and namespaces."""

import os as _os
from pathlib import Path as path

from . import log, toml
from .install import install, uninstall


def env(name, default=None):
    """Return one environment variable."""
    return _os.environ.get(name, default)


def envs():
    """Return a snapshot of the current environment."""
    return dict(_os.environ)
