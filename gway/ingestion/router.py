"""Ingestion routing across source kinds."""

import os
from pathlib import Path, PureWindowsPath
from types import ModuleType


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


def ingest(gateway, source, **kwargs):
    """Route an explicitly requested ingestion source to its ingestor."""
    kind = kwargs.pop("kind", None)

    from .url import ingest_url, is_url

    if is_url(source):
        return ingest_url(gateway, source, **kwargs)

    if kind == "proc":
        from .proc import ingest_proc

        return ingest_proc(gateway, source, **kwargs)

    if kind == "python":
        if isinstance(source, str):
            from .python import ingest_name

            return ingest_name(gateway, source, **kwargs)

    if kind == "django":
        from .django import ingest_orm, ingest_project, source_kind

        if source_kind(source) is not None:
            return ingest_orm(gateway, source, **kwargs)
        return ingest_project(gateway, source, **kwargs)

    if _is_pathlike(source):
        return ingest_path(gateway, source, **kwargs)

    if isinstance(source, str):
        from .python import ingest_name

        try:
            return ingest_name(gateway, source, **kwargs)
        except ModuleNotFoundError as error:
            if error.name != source.split(".", 1)[0]:
                raise
            from .proc import ingest_proc

            return ingest_proc(gateway, source, **kwargs)

    if isinstance(source, ModuleType):
        from .python import ingest_module

        return ingest_module(gateway, source, **kwargs)

    from .django import ingest_orm, source_kind

    if source_kind(source) is not None:
        return ingest_orm(gateway, source, **kwargs)

    from .python import ingest_python

    return ingest_python(gateway, source, **kwargs)


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
