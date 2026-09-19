"""Incremental one-level ingestion for Python sources."""

from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
import inspect
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
    """Yield direct public attributes plus the module __main__ convention."""
    try:
        names = dir(source)
    except Exception:
        return

    for name in names:
        if name.startswith("_") and name != "__main__":
            continue
        try:
            value = getattr(source, name)
        except Exception:
            continue
        yield name, value


def _receiver_subject(source, root, name, child):
    """Return the semantic receiver for one unbound instance method."""
    if not inspect.isclass(source):
        return None

    try:
        descriptor = inspect.getattr_static(source, name)
    except AttributeError:
        return None

    if isinstance(descriptor, (staticmethod, classmethod)):
        return None

    try:
        parameters = tuple(inspect.signature(child).parameters.values())
    except (TypeError, ValueError):
        return None

    if not parameters:
        return None

    first = parameters[0]
    if first.kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        return None
    return root[-1]


def _child_operation(source, root, name, child):
    """Describe one callable child and any semantic instance receiver."""
    metadata = {"object": child}
    receiver = _receiver_subject(source, root, name, child)
    if receiver is not None:
        metadata["receiver"] = receiver

    return IngestedOperation(
        (*root, name),
        child,
        source=source,
        kind="python",
        metadata=metadata,
    )


def _operation(source, root, name, child):
    """Describe one callable using module entry semantics when applicable."""
    if root and isinstance(source, ModuleType) and callable(getattr(source, "__main__", None)):
        if name == "__main__":
            path = root
            op = root[-1]
            sub = None
        else:
            path = (*root, name)
            op = root[-1]
            sub = name
    elif inspect.isclass(child):
        path = (*root, name)
        op = name
        sub = name
    else:
        path = (*root, name)
        op = None
        sub = None

    return IngestedOperation(
        path,
        child,
        source=source,
        kind="python",
        op=op,
        sub=sub,
        metadata={"object": child},
    )


def discover_module(source, *, path=None, transparent=False):
    """Describe direct callables in a Python module namespace."""
    if not isinstance(source, ModuleType):
        raise TypeError("source must be a Python module")
    source_root = normalize_path(path) if path is not None else _default_path(source)
    root = () if transparent else source_root
    return [
        _operation(source, root, name, child)
        for name, child in _public_members(source)
        if callable(child) and not (transparent and name == "__main__")
    ]


def discover_python(source, *, path=None):
    """Describe callable values in exactly one Python namespace level."""
    if isinstance(source, ModuleType):
        return discover_module(source, path=path)

    root = normalize_path(path) if path is not None else _default_path(source)
    discovered = []

    if callable(source):
        discovered.append(
            IngestedOperation(
                root,
                source,
                source=source,
                kind="python",
                op=root[-1] if inspect.isclass(source) else None,
                sub=root[-1] if inspect.isclass(source) else None,
                metadata={"object": source},
            )
        )

    for name, child in _public_members(source):
        if callable(child):
            discovered.append(_child_operation(source, root, name, child))

    return discovered


def _register_callable(gateway, record, operation):
    """Register one callable identity once and alias any additional paths."""
    if record.operation is None:
        wrapped = register_operation(gateway, operation)
        record.operation = wrapped
        record.registered = True
        return wrapped

    gateway.ops.register(
        operation.name,
        record.operation,
        op=operation.op,
        sub=operation.sub,
    )
    return None


def _remember_child(gateway, child, path):
    expander = ingest_module if isinstance(child, ModuleType) else ingest_python
    return remember_object(gateway, child, path, expander=expander)


def ingest_module(gateway, source, *, path=None, transparent=False, **kwargs):
    """Expand exactly one Python module namespace."""
    if not isinstance(source, ModuleType):
        raise TypeError("source must be a Python module")

    source_root = normalize_path(path) if path is not None else _default_path(source)
    root = () if transparent else source_root
    source_record = remember_object(
        gateway,
        source,
        source_root,
        expander=ingest_module,
    )
    if source_record.expanded:
        return []

    wrapped = []
    for name, child in _public_members(source):
        if transparent and name == "__main__":
            continue
        child_path = (*root, name)
        child_record = _remember_child(gateway, child, child_path)
        if callable(child):
            operation = _operation(source, root, name, child)
            registered = _register_callable(gateway, child_record, operation)
            if registered is not None:
                wrapped.append(registered)

    source_record.expanded = True
    return wrapped


def ingest_python(gateway, source, *, path=None, **kwargs):
    """Expand one imported Python object namespace and register direct callables."""
    if isinstance(source, ModuleType):
        return ingest_module(gateway, source, path=path, **kwargs)

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
            op=root[-1] if inspect.isclass(source) else None,
            sub=root[-1] if inspect.isclass(source) else None,
            metadata={"object": source},
        )
        registered = _register_callable(gateway, source_record, operation)
        if registered is not None:
            wrapped.append(registered)

    for name, child in _public_members(source):
        child_path = (*root, name)
        child_record = _remember_child(gateway, child, child_path)
        if callable(child):
            operation = _child_operation(source, root, name, child)
            registered = _register_callable(gateway, child_record, operation)
            if registered is not None:
                wrapped.append(registered)

    source_record.expanded = True
    return wrapped


def ingest_name(gateway, name, *, path=None, **kwargs):
    """Import and ingest a fully qualified Python module/package name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Python import name must be a non-empty string")

    module = import_module(name)
    return ingest_module(gateway, module, path=path, **kwargs)


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
    """Load and ingest Python from a module file or package path."""
    module = _load_path(path, name=name)
    return ingest_module(gateway, module, path=root, **kwargs)
