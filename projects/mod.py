# file: projects/mod.py
"""Alias to the :mod:`projects.model` project."""

from .model import list_models, __getattr__

__all__ = ["list_models", "__getattr__"]
