"""Built-in GWAY operations and namespaces."""

from pathlib import Path as path

from . import log, security, test, toml
from .environment import environment_snapshot, environment_value
from .install import install, uninstall


def env(name, default=None):
    """Return one environment variable.

    Args:
        name: Environment variable name to read.
        default: Value returned when the variable is not defined.
    """
    return environment_value(name, default)


def envs():
    """Return a snapshot of the current environment."""
    return environment_snapshot()
