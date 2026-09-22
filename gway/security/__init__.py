"""Reusable GWAY security primitives."""

from . import scopes as scope
from .scopes import EffectiveScope, Scope, ScopeRegistry
from .state import SecurityState

__all__ = [
    "EffectiveScope",
    "Scope",
    "ScopeRegistry",
    "SecurityState",
    "scope",
]
