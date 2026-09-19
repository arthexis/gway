"""Minimal install metadata reader with optional full TOML support."""

import ast
from pathlib import Path

from .. import toml


_SECTIONS = {"project", "project.scripts", "install.scripts"}


def _fallback(path):
    """Read only string values used by the install contract."""
    result = {
        "project": {"scripts": {}},
        "install": {"scripts": {}},
    }
    section = None

    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section not in _SECTIONS or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().strip('"').strip("'")
        value = value.strip()
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            continue
        if not isinstance(parsed, str):
            continue

        if section == "project":
            result["project"][key] = parsed
        elif section == "project.scripts":
            result["project"]["scripts"][key] = parsed
        elif section == "install.scripts":
            result["install"]["scripts"][key] = parsed

    return result


def load(path):
    """Load install metadata without making TOML a core dependency."""
    try:
        return toml.load(path)
    except ModuleNotFoundError as exc:
        if exc.name != "tomli":
            raise
        return _fallback(path)
