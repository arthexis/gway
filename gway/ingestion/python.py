"""Recursive ingestion for already-imported Python sources."""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

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


def _load_path(path, *, name=None):
    """Load one Python module or package directly from a filesystem path."""
    path = Path(path).expanduser().resolve()

    if path.is_dir():
        init = path / "__init__.py"
        if not init.is_file():
            raise ValueError(f"Python package path has no __init__.py: {path}")
        module_name = name or path.name
        spec = spec_from_file_location(
            module_name,
            init,
            submodule_search_locations=[str(path)],
        )
    elif path.is_file() and path.suffix == ".py":
        module_name = name or path.stem
        spec = spec_from_file_location(module_name, path)
    else:
        raise ValueError(f"Unsupported Python path: {path}")

    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load Python source from {path}")

    module = module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module


def ingest_path(gateway, path, *, name=None, root=None, **kwargs):
    """Load and recursively ingest Python from a module file or package path."""
    module = _load_path(path, name=name)
    return ingest_python(gateway, module, path=root, **kwargs)
