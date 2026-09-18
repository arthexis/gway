"""Compatibility facade for the logging command.

The implementation is owned by :mod:`gway.logs.command`. This module remains
temporarily importable for callers that used the pre-package location.
"""

from .logs.command import run_log

__all__ = ["run_log"]
