"""Central process-environment substrate.

This module is the only production boundary that directly touches os.environ.
Semantic configuration must not grow new dependencies on this API; literal-name
reads outside interoperability paths are transitional until #1019 E6/E8 removes
them.
"""

from collections.abc import Mapping
import os

# Transitional literal configuration reads consolidated during E1. E8 must drive
# this inventory to empty rather than treating this module as a permanent escape
# hatch for semantic configuration.
TRANSITIONAL_DIRECT_ENVIRONMENT_FILES = frozenset({("sampler", "mcp", "server.py")})

BACKEND_ENVIRONMENT = frozenset(
    {
        "GWAY_SECRETS_DIR",
    }
)

TRANSITIONAL_SEMANTIC_ENVIRONMENT = frozenset(
    {
        "DJANGO_SETTINGS_MODULE",
        "GWAY_BIN_DIR",
        "GWAY_DATA_DIR",
        "GWAY_MCP_ENDPOINT",
        "GWAY_MCP_PUBLIC_ORIGIN",
        "GWAY_SYSTEM_BIN_DIR",
        "GWAY_SYSTEM_DATA_DIR",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
    }
)


class ProcessEnvironment(Mapping):
    """Literal process-environment access and child-environment construction."""

    def __getitem__(self, name):
        return os.environ[str(name)]

    def __iter__(self):
        return iter(os.environ)

    def __len__(self):
        return len(os.environ)

    def get(self, name, default=None):
        return os.environ.get(str(name), default)

    def names(self):
        return tuple(os.environ)

    def snapshot(self):
        return dict(os.environ)

    def set(self, name, value):
        os.environ[str(name)] = str(value)
        return str(value)

    def setdefault(self, name, value):
        return os.environ.setdefault(str(name), str(value))

    def remove(self, name):
        return os.environ.pop(str(name), None)

    def child(self, *, overrides=None, removals=()):
        environment = self.snapshot()
        for name in removals:
            environment.pop(str(name), None)
        for name, value in dict(overrides or {}).items():
            if value is None:
                environment.pop(str(name), None)
            else:
                environment[str(name)] = str(value)
        return environment

    def restore(self, name, previous):
        if previous is None:
            self.remove(name)
        else:
            self.set(name, previous)


process_environment = ProcessEnvironment()


def environment_value(name, default=None):
    """Return one literal process-environment value."""
    return process_environment.get(name, default)


def environment_names():
    """Return the current literal process-environment names."""
    return process_environment.names()


def environment_snapshot():
    """Return an isolated process-environment snapshot."""
    return process_environment.snapshot()


def environment_child(*, overrides=None, removals=()):
    """Return a child-process environment with literal overrides/removals."""
    return process_environment.child(overrides=overrides, removals=removals)
