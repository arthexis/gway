"""Ingestion routing across source kinds."""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType


def _is_explicit_path_string(source):
    """Return whether string syntax explicitly identifies a filesystem location."""
    if not isinstance(source, str) or not source:
        return False

    # Shell/home rooted forms are explicit even though '~' is expanded later.
    if source == "~" or source.startswith(("~/", "~\\")):
        return True

    # Explicit current/parent roots are paths; incidental dots are not.
    if source in {".", ".."} or source.startswith(("./", "../", ".\\", "..\\")):
        return True

    # Recognize absolute syntax independently of the host platform so routing
    # itself is deterministic for POSIX, drive-rooted, and UNC spellings.
    return (
        PurePosixPath(source).is_absolute()
        or PureWindowsPath(source).is_absolute()
    )


def _is_pathlike(source):
    """Return whether ingest() should delegate this source to ingest_path()."""
    if isinstance(source, os.PathLike):
        return True
    return _is_explicit_path_string(source)


def ingest(gateway, source, **kwargs):
    """Route an ingestion source to the appropriate ingestor."""
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
