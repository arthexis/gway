"""Compatibility alias for :mod:`gway.checkpoint.chain`."""

from .checkpoint import chain as _chain
import sys as _sys

_sys.modules[__name__] = _chain
