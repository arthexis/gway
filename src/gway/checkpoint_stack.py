"""Compatibility alias for :mod:`gway.checkpoint.stack`."""

from .checkpoint import stack as _stack
import sys as _sys

_sys.modules[__name__] = _stack
