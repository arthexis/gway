"""Ingestion routing across source kinds."""

import os
from pathlib import Path
from types import ModuleType


def _is_pathlike(source):
    if isinstance(source, os.PathLike):
        return True
    if not isinstance(source, str):
        return False
    return (
        source.startswith((".", "/", "~"))
        or os.sep in source
        or (os.altsep is not None and os.altsep in source)
        or Path(source).exists()
    )


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
