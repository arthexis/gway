"""Python source ingestion.

The traversal implementation is intentionally deferred. These entry points
define the supported source forms for the Python ingestor.
"""

from pathlib import Path


def ingest_python(gateway, source, **kwargs):
    """Ingest an imported module/package, class, function, or object."""
    raise NotImplementedError("Python object ingestion is not implemented yet")


def ingest_name(gateway, name, **kwargs):
    """Import and ingest a fully qualified Python module/package name."""
    raise NotImplementedError("Python name ingestion is not implemented yet")


def ingest_path(gateway, path, **kwargs):
    """Load and ingest Python from a module file or package path."""
    path = Path(path)
    raise NotImplementedError(f"Python path ingestion is not implemented yet: {path}")
