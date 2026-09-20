"""Version-independent TOML operations for GWAY."""

import sys as _sys
from importlib import import_module as _import_module


def _backend():
    """Return the TOML implementation appropriate for this Python version."""
    if _sys.version_info >= (3, 11):
        return _import_module("tomllib")
    return _import_module("tomli")


def loads(value):
    """Parse TOML text into a Python mapping.

    Args:
        value: Complete TOML document text.
    """
    return _backend().loads(value)


def load(path):
    """Parse a TOML file from a filesystem path.

    Args:
        path: Path to a TOML document opened and parsed as binary input.
    """
    with open(path, "rb") as stream:
        return _backend().load(stream)


def __main__(value):
    """Parse TOML text using the stable top-level toml operation.

    Args:
        value: Complete TOML document text.
    """
    return loads(value)
