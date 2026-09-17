"""Compatibility alias for :mod:`gway.checkpoint.store`."""

from __future__ import annotations

import sys

from .checkpoint import store as _store

sys.modules[__name__] = _store
