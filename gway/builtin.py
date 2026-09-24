"""Built-in GWAY operations and namespaces."""

from pathlib import Path as path

from . import log, security, test, toml
from .interop import environment as literal_environment
from .install import install, uninstall


def env(name, default=None):
    """Return one environment variable.

    Args:
        name: Environment variable name to read.
        default: Value returned when the variable is not defined.
    """
    return literal_environment.read(name, default)


def envs():
    """Return a snapshot of the current environment."""
    return literal_environment.snapshot()
