"""GWAY builtin functions grouped by category."""
from importlib import import_module
from pkgutil import iter_modules

__all__ = []

for modinfo in iter_modules(__path__):
    if modinfo.ispkg:
        continue
    mod = import_module(f"{__name__}.{modinfo.name}")
    names = getattr(mod, "__all__", [n for n in dir(mod) if not n.startswith("_")])
    for name in names:
        globals()[name] = getattr(mod, name)
        __all__.append(name)
