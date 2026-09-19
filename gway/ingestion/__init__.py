"""Shared ingestion primitives and routing."""

from .base import (
    IngestedOperation,
    canonical_name,
    normalize_path,
    register_operation,
    register_operations,
)
from .python import ingest_module
from .router import ingest, ingest_path

__all__ = [
    "IngestedOperation",
    "canonical_name",
    "ingest",
    "ingest_module",
    "ingest_path",
    "normalize_path",
    "register_operation",
    "register_operations",
]
