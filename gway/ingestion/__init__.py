"""Shared ingestion primitives."""

from .base import (
    IngestedOperation,
    canonical_name,
    normalize_path,
    register_operation,
    register_operations,
)

__all__ = [
    "IngestedOperation",
    "canonical_name",
    "normalize_path",
    "register_operation",
    "register_operations",
]
