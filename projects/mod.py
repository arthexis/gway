# file: projects/mod.py
"""Alias to the :mod:`projects.model` project."""

# Load directly from the ``projects`` package so the module can be executed
# standalone without package context.
from projects import model as _model

list_models = _model.list_models
__getattr__ = _model.__getattr__

__all__ = ["list_models", "__getattr__"]
