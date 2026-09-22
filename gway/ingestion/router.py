"""Ingestion routing across source kinds."""

import os
from pathlib import Path, PureWindowsPath
from types import ModuleType

from .base import canonical_name, normalize_path


def has_path_syntax(source):
    """Return whether a string explicitly spells filesystem path intent."""
    if not isinstance(source, str) or not source:
        return False
    if "/" in source or "\\" in source:
        return True
    if source.startswith("~"):
        return True
    if PureWindowsPath(source).drive:
        return True
    return False


def _is_path_string(source):
    """Return whether an explicit ingest string denotes a filesystem source."""
    if not isinstance(source, str) or not source:
        return False
    if has_path_syntax(source):
        return True

    # A bare spelling has no syntactic path marker. Inside explicit ingest(),
    # filesystem existence is the final disambiguator.
    return Path(source).exists()


def _is_pathlike(source):
    """Return whether ingest() should delegate this source to ingest_path()."""
    if isinstance(source, os.PathLike):
        return True
    return _is_path_string(source)


def _common_root(paths):
    """Return the longest shared path prefix for ingested operations."""
    if not paths:
        return ()
    prefix = list(paths[0])
    for path in paths[1:]:
        size = min(len(prefix), len(path))
        index = 0
        while index < size and prefix[index] == path[index]:
            index += 1
        del prefix[index:]
        if not prefix:
            break
    return tuple(prefix)


def _apply_aka(gateway, result, aka):
    """Expose an ingested source under one additional semantic root."""
    if aka is None:
        return result

    alias_root = normalize_path(aka)
    if isinstance(result, (list, tuple, set)):
        wrapped = [
            item
            for item in result
            if callable(item) and getattr(item, "__gway_path__", None)
        ]
    elif callable(result) and getattr(result, "__gway_path__", None):
        wrapped = [result]
    else:
        wrapped = []

    paths = [tuple(item.__gway_path__) for item in wrapped]
    source_root = _common_root(paths)
    if not source_root:
        raise ValueError("AKA requires an ingested callable source")

    aliases = []
    for item, path in zip(wrapped, paths):
        relative = path[len(source_root) :]
        alias = canonical_name((*alias_root, *relative))
        existing = gateway.ops.resolve(alias)
        if existing is not None and existing is not item:
            raise ValueError(f"AKA conflicts with existing operation: {alias}")
        aliases.append((alias, item))

    for alias, item in aliases:
        gateway.ops.register_alias(alias, item)

    # Preserve lazy/JIT reachability through the AKA root as well. Records may
    # include non-callable namespace children that are expanded only on demand.
    for record in gateway._ingested.values():
        extra = set()
        for path in record.paths:
            if path[: len(source_root)] != source_root:
                continue
            relative = path[len(source_root) :]
            extra.add((*alias_root, *relative))
        record.paths.update(extra)

    return result


def ingest(gateway, source, **kwargs):
    """Route an explicitly requested ingestion source to its ingestor."""
    kind = kwargs.pop("kind", None)
    aka = kwargs.pop("aka", None)
    if aka is not None:
        # Validate before performing the source-specific ingestion.
        normalize_path(aka)

    def finish(result):
        return _apply_aka(gateway, result, aka)

    from .url import ingest_url, is_url

    if is_url(source):
        return finish(ingest_url(gateway, source, **kwargs))

    if kind == "proc":
        from .proc import ingest_proc

        return finish(ingest_proc(gateway, source, **kwargs))

    if kind == "python":
        if isinstance(source, str):
            from .python import ingest_name

            return finish(ingest_name(gateway, source, **kwargs))

    if kind == "django":
        from .django import ingest_orm, ingest_project, source_kind

        if source_kind(source) is not None:
            return finish(ingest_orm(gateway, source, **kwargs))
        return finish(ingest_project(gateway, source, **kwargs))

    if _is_pathlike(source):
        return finish(ingest_path(gateway, source, **kwargs))

    if isinstance(source, str):
        from .python import ingest_name

        try:
            return finish(ingest_name(gateway, source, **kwargs))
        except ModuleNotFoundError as error:
            if error.name != source.split(".", 1)[0]:
                raise
            from .proc import ingest_proc

            return finish(ingest_proc(gateway, source, **kwargs))

    if isinstance(source, ModuleType):
        from .python import ingest_module

        return finish(ingest_module(gateway, source, **kwargs))

    from .django import ingest_orm, source_kind

    if source_kind(source) is not None:
        return finish(ingest_orm(gateway, source, **kwargs))

    from .python import ingest_python

    return finish(ingest_python(gateway, source, **kwargs))


def ingest_path(gateway, path, **kwargs):
    """Route a filesystem path by structural source type."""
    path = Path(path).expanduser()

    from .django import is_project_path

    if is_project_path(path):
        from .django import ingest_project as ingest_django_project

        return ingest_django_project(gateway, path, **kwargs)

    if path.suffix == ".py" or path.is_dir():
        from .python import ingest_path as ingest_python_path

        return ingest_python_path(gateway, path, **kwargs)

    if path.is_file() and os.access(path, os.X_OK):
        from .proc import ingest_path as ingest_proc_path

        return ingest_proc_path(gateway, path, **kwargs)

    raise ValueError(f"Unsupported ingestion path: {path}")
