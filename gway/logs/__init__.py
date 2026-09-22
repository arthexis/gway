"""Structured logging domain for GWAY-managed log sources."""

from .discovery import installed_sources
from .identity import (
    gway_identity,
    project_identity,
    recipe_identity,
    service_identity,
)
from .journal import JournalError, read_journal
from .model import LogRecord
from .source import LogSource


__all__ = [
    "JournalError",
    "LogRecord",
    "LogSource",
    "gway_identity",
    "installed_sources",
    "project_identity",
    "read_journal",
    "recipe_identity",
    "service_identity",
]
