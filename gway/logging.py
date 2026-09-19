"""Logging primitives and logger hierarchy for GWAY."""

from itertools import count as _count
from logging import (
    CRITICAL as _CRITICAL,
    INFO as _INFO,
    NOTSET as _NOTSET,
    critical,
    error,
    exception,
    getLogger as _get_logger,
    info,
    warning,
)

logger = _get_logger("gway")
logger.setLevel(_NOTSET)
_instances = _count()


def _child(name="gw"):
    """Return a unique logger below the parent GWAY logger."""
    return logger.getChild(f"{name}.{next(_instances)}")


def _level(*, verbose=False, silent=False):
    """Return the runtime logger level for the active verbosity policy."""
    if silent:
        return _CRITICAL + 1
    if verbose:
        return _INFO
    return _NOTSET
