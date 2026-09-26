"""Built-in GWAY operations and namespaces."""

from pathlib import Path as path
from importlib.metadata import version as _package_version

from . import log, security, test, toml
from .interop import environment as literal_environment
from .install import install, uninstall


def version(*, mutate=False):
    """Return the installed GWAY package version."""
    return _package_version("gway")


def env(name, default=None, *, mutate=False):
    """Return one environment variable.

    Args:
        name: Environment variable name to read.
        default: Value returned when the variable is not defined.
    """
    return literal_environment.read(name, default)


def envs(*, mutate=False):
    """Return a snapshot of the current environment."""
    return literal_environment.snapshot()
