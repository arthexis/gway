"""Built-in logging operations and GWAY logger hierarchy."""

from itertools import count as _count
from logging import (
    CRITICAL as _CRITICAL,
    INFO as _INFO,
    NOTSET as _NOTSET,
    critical,
    debug,
    error,
    exception,
    getLogger as _get_logger,
    info,
    log as _log,
    warning,
)

logger = _get_logger("gway")
logger.setLevel(_NOTSET)
_instances = _count()


def warn(message, *args, **kwargs):
    """Alias the legacy warn subject to logging.warning without using logging.warn."""
    return warning(message, *args, **kwargs)


def __main__(message, *args, level: int = _INFO, **kwargs):
    """Log a message at an explicit level, defaulting to INFO."""
    return _log(level, message, *args, **kwargs)


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
