"""Compatibility shim for legacy ``gw.studio.screen`` imports.

Prefer accessing these helpers via the top-level :mod:`projects.screen`
module instead (``gw.screen``).
"""

from importlib import import_module as _import_module

_screen = _import_module("projects.screen")

__all__ = getattr(_screen, "__all__", None)
if __all__ is None:
    __all__ = [name for name in dir(_screen) if not name.startswith("_")]

for name in __all__:
    globals()[name] = getattr(_screen, name)
