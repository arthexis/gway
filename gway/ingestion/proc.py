"""Generic process ingestion.

Process ingestion will expose an executable as a generic argv-preserving
operation root. Execution behavior is intentionally deferred.
"""

from pathlib import Path


def ingest_proc(gateway, executable, **kwargs):
    """Ingest a generic executable/process root."""
    raise NotImplementedError("Process ingestion is not implemented yet")


def ingest_path(gateway, path, **kwargs):
    """Ingest an executable from a filesystem path."""
    path = Path(path)
    raise NotImplementedError(f"Process path ingestion is not implemented yet: {path}")
