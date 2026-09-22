"""Structured logging domain for GWAY-managed log sources."""

from .identity import (
    gway_identity,
    project_identity,
    recipe_identity,
    service_identity,
)
from .model import LogRecord
from .source import LogSource


__all__ = [
    "LogRecord",
    "LogSource",
    "gway_identity",
    "project_identity",
    "recipe_identity",
    "service_identity",
]
