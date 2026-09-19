"""Recursive ingestion for already-imported Python sources."""

from importlib import import_module
from pathlib import Path

from .base import IngestedOperation, normalize_path, register_operations


def _default_path(source):
    name = getattr(source, "__name__", None)
    if isinstance(name, str) and name:
        return tuple(part for part in name.split(".") if part)

    cls = type(source)
    name = getattr(cls, "__name__", None)
    if isinstance(name, str) and name:
        return (name,)

    raise ValueError("Python source requires an explicit ingestion path")


def _public_members(source):
    """Yield reachable public attributes, ignoring attributes that cannot be read."""
    try:
        names = dir(source)
    except Exception:
        return

    for name in names:
        if name.startswith("_"):
            continue
        try:
            value = getattr(source, name)
        except Exception:
            continue
        yield name, value


def discover_python(source, *, path=None):
    """Discover callable Python values reachable from an imported source."""
    root = normalize_path(path) if path is not None else _default_path(source)
    discovered = []
    expanded = set()

    def walk(value, current_path):
        if callable(value):
            discovered.append(
                IngestedOperation(
                    current_path,
                    value,
                    source=source,
                    kind="python",
                    metadata={"object": value},
                )
            )

        identity = id(value)
        if identity in expanded:
            return
        expanded.add(identity)

        for name, child in _public_members(value):
            walk(child, (*current_path, name))

    walk(source, root)
    return discovered


def ingest_python(gateway, source, *, path=None, **kwargs):
    """Recursively ingest an imported module/package, class, function, or object."""
    operations = discover_python(source, path=path)
    return register_operations(gateway, operations)


def ingest_name(gateway, name, *, path=None, **kwargs):
    """Import and recursively ingest a fully qualified Python module/package name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Python import name must be a non-empty string")

    module = import_module(name)
    return ingest_python(gateway, module, path=path, **kwargs)


def ingest_path(gateway, path, **kwargs):
    """Load and ingest Python from a module file or package path."""
    path = Path(path)
    raise NotImplementedError(f"Python path ingestion is not implemented yet: {path}")
