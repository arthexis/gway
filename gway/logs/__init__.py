"""Structured logging domain for GWAY-managed log sources."""

from .catalog import UnknownLogSource, resolve_sources, source_catalog
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
    "UnknownLogSource",
    "gway_identity",
    "installed_sources",
    "project_identity",
    "read_journal",
    "resolve_sources",
    "recipe_identity",
    "service_identity",
    "source_catalog",
]
