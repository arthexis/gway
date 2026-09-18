# file: projects/cli.py
"""CLI helper utilities.

This project provides functions related to the command
line interface. The ``completions`` function is a prototype
to inspect available project commands for custom shell
completion scripts.
"""

from __future__ import annotations

import inspect
from gway import gw
from gway.structs import Project


def _walk(ns: Project, parts: list[str]) -> list[list[str]]:
    commands: list[list[str]] = []
    for name in dir(ns):
        if name.startswith("_"):
            continue
        obj = getattr(ns, name)
        if isinstance(obj, Project):
            commands.extend(_walk(obj, parts + [name]))
        elif inspect.isfunction(obj):
            commands.append(parts + [name])
    return commands


def completions() -> list[str]:
    """Return a list of available command paths, including builtins."""

    commands: list[str] = []

    # builtins appear as top-level commands
    for name in gw.builtins():
        commands.append(name.replace("_", "-"))

    # discover project functions recursively
    for proj in gw.projects():
        try:
            project = gw.load_project(proj)
        except Exception:
            continue
        for parts in _walk(project, [proj]):
            commands.append(" ".join(p.replace("_", "-") for p in parts))

    return sorted(commands)

