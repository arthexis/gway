"""Structured logging domain for GWAY-managed log sources."""

from .catalog import UnknownLogSource, resolve_sources, source_catalog
from .discovery import installed_sources
from .file import FileLogError, read_file_logs
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
    "FileLogError",
    "JournalError",
    "LogRecord",
    "LogSource",
    "UnknownLogSource",
    "gway_identity",
    "installed_sources",
    "project_identity",
    "read_file_logs",
    "read_journal",
    "resolve_sources",
    "recipe_identity",
    "service_identity",
    "source_catalog",
]
