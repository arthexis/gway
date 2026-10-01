"""Compatibility imports for the sampler-owned GitHub operations.

GitHub registration and implementation live under ``sampler/github``. This module
remains only so existing Python imports keep working during the migration.
"""

from .sampler import load

_github = load("github")

Controller = _github.Controller
ADMIN_OPERATIONS = _github.ADMIN_OPERATIONS
WRITE_OPERATIONS = _github.WRITE_OPERATIONS

__all__ = ["ADMIN_OPERATIONS", "Controller", "WRITE_OPERATIONS"]
