"""Ingestion routing across source kinds."""

import os
from pathlib import Path, PureWindowsPath
from types import ModuleType


def _is_path_string(source):
    """Return whether an explicit ingest string denotes a filesystem source."""
    if not isinstance(source, str) or not source:
        return False

    # Path separators make relative intent explicit even when the target does
    # not exist yet. Support both separator spellings independent of host OS.
    if "/" in source or "\\" in source:
        return True

    # Shell/home syntax is path intent even without a separator.
    if source.startswith("~"):
        return True

    # Windows drive-qualified spellings such as C:README are path-shaped even
    # when they are drive-relative rather than absolute.
    if PureWindowsPath(source).drive:
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
    if _is_pathlike(source):
        return ingest_path(gateway, source, **kwargs)

    if isinstance(source, str):
        from .python import ingest_name

        return ingest_name(gateway, source, **kwargs)

    if isinstance(source, ModuleType):
        from .python import ingest_module

        return ingest_module(gateway, source, **kwargs)

    from .python import ingest_python

    return ingest_python(gateway, source, **kwargs)


def ingest_path(gateway, path, **kwargs):
    """Route a filesystem path by structural source type."""
    path = Path(path).expanduser()

    if path.suffix == ".py" or path.is_dir():
        from .python import ingest_path as ingest_python_path

        return ingest_python_path(gateway, path, **kwargs)

    if path.is_file() and os.access(path, os.X_OK):
        from .proc import ingest_path as ingest_proc_path

        return ingest_proc_path(gateway, path, **kwargs)

    raise ValueError(f"Unsupported ingestion path: {path}")
