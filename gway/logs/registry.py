"""Persistent registry for recipe-owned log sources."""

import json
import os
from pathlib import Path
import tempfile

from .identity import recipe_identity
from .source import LogSource


_FILENAME = "recipe-log-sources.json"


def _path(root):
    return Path(root).expanduser().resolve() / "logs" / _FILENAME


def register_recipe_source(identity, *, root):
    """Persist one canonical recipe log source below a Gway data root."""
    canonical = recipe_identity(str(identity).removeprefix("recipe/"))
    path = _path(root)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        existing = []
    values = sorted({*(str(item) for item in existing if str(item)), canonical})
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".recipe-log-sources.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(values, stream, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return canonical


def recipe_sources(*roots):
    """Return persisted concrete recipe log sources across readable roots."""
    identities = set()
    for root in roots:
        try:
            values = json.loads(_path(root).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                identities.add(recipe_identity(str(value).removeprefix("recipe/")))
            except (TypeError, ValueError):
                continue
    return [
        LogSource(
            identity=identity,
            kind="recipe",
            backend="journal",
            backend_id=identity,
        )
        for identity in sorted(identities)
    ]
