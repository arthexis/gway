"""Incremental one-level ingestion for Python sources."""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from .base import (
    IngestedOperation,
    normalize_path,
    register_operation,
    remember_object,
)


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
    """Yield direct public attributes, ignoring attributes that cannot be read."""
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
    """Describe callable values in exactly one Python namespace level."""
    root = normalize_path(path) if path is not None else _default_path(source)
    discovered = []

    if callable(source):
        discovered.append(
            IngestedOperation(
                root,
                source,
                source=source,
                kind="python",
                metadata={"object": source},
            )
        )

    for name, child in _public_members(source):
        if callable(child):
            discovered.append(
                IngestedOperation(
                    (*root, name),
                    child,
                    source=source,
                    kind="python",
                    metadata={"object": child},
                )
            )

    return discovered


def _register_callable(gateway, record, operation):
    """Register one callable identity once and alias any additional paths."""
    if record.operation is None:
        wrapped = register_operation(gateway, operation)
        record.operation = wrapped
        record.registered = True
        return wrapped

    gateway.ops.register_alias(operation.name, record.operation)
    return None


def ingest_python(gateway, source, *, path=None, **kwargs):
    """Expand one imported Python object namespace and register direct callables."""
    root = normalize_path(path) if path is not None else _default_path(source)
    source_record = remember_object(
        gateway,
        source,
        root,
        expander=ingest_python,
    )
    if source_record.expanded:
        return []

    wrapped = []

    if callable(source):
        operation = IngestedOperation(
            root,
            source,
            source=source,
            kind="python",
            metadata={"object": source},
        )
        registered = _register_callable(gateway, source_record, operation)
        if registered is not None:
            wrapped.append(registered)

    for name, child in _public_members(source):
        child_path = (*root, name)
        child_record = remember_object(
            gateway,
            child,
            child_path,
            expander=ingest_python,
        )
        if callable(child):
            operation = IngestedOperation(
                child_path,
                child,
                source=source,
                kind="python",
                metadata={"object": child},
            )
            registered = _register_callable(gateway, child_record, operation)
            if registered is not None:
                wrapped.append(registered)

    source_record.expanded = True
    return wrapped


def ingest_name(gateway, name, *, path=None, **kwargs):
    """Import and incrementally ingest a fully qualified Python module/package name."""
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
    """Load and incrementally ingest Python from a module file or package path."""
    module = _load_path(path, name=name)
    return ingest_python(gateway, module, path=root, **kwargs)
