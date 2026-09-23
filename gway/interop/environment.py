"""Literal environment interoperability surface.

This module exposes environment-as-environment behavior for commands and
external interfaces whose contract is the literal process environment. It is
not a semantic configuration API.
"""

from ..environment import environment_snapshot, environment_value


def read(name, default=None):
    """Read one literal process-environment value."""
    return environment_value(name, default)


def snapshot():
    """Return one isolated literal process-environment snapshot."""
    return environment_snapshot()
