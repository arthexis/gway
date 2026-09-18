"""Generic package upgrade helpers."""

from __future__ import annotations

from importlib import import_module
from types import FunctionType

_helpers = import_module(".__package__", __name__)
__all__ = list(getattr(_helpers, "__all__", ()))

for attr, value in vars(_helpers).items():
    if attr == "__all__" or attr.startswith("__"):
        continue
    if isinstance(value, FunctionType):
        clone = FunctionType(
            value.__code__,
            globals(),
            name=value.__name__,
            argdefs=value.__defaults__,
            closure=value.__closure__,
        )
        clone.__kwdefaults__ = getattr(value, "__kwdefaults__", None)
        clone.__doc__ = value.__doc__
        clone.__annotations__ = getattr(value, "__annotations__", {})
        clone.__qualname__ = value.__qualname__
        clone.__module__ = __name__
        value = clone
    globals()[attr] = value

