"""Built-in logging operations and GWAY logger hierarchy."""

from itertools import count as _count
import logging as _logging


_DEFAULT_LEVEL = _logging.WARNING
_gway_logger = _logging.getLogger("gway")
_gway_logger.setLevel(_DEFAULT_LEVEL)
logger = _gway_logger
_instances = _count()


def _coerce_level(level):
    """Return a logging level number from a conventional name or integer."""
    if isinstance(level, int):
        return level
    if not isinstance(level, str) or not level.strip():
        raise ValueError("log level must be a name or integer")
    value = level.strip().upper()
    try:
        return int(value)
    except ValueError:
        numeric = _logging.getLevelName(value)
        if isinstance(numeric, int):
            return numeric
        raise ValueError(f"Unknown log level: {level}")


class _Level:
    """A logging level that is both callable and truth-testable."""

    def __init__(self, target, level, *, exc_info=False):
        self.logger = target
        self.level = _coerce_level(level)
        self.exc_info = exc_info

    def __bool__(self):
        return self.logger.isEnabledFor(self.level)

    def __call__(self, message, *args, **kwargs):
        if self.exc_info:
            kwargs.setdefault("exc_info", True)
        return self.logger.log(self.level, message, *args, **kwargs)

    @property
    def name(self):
        return _logging.getLevelName(self.level)


def _levels(target):
    """Return the standard callable/boolean level objects for one logger."""
    warning = _Level(target, _logging.WARNING)
    return {
        "debug": _Level(target, _logging.DEBUG),
        "info": _Level(target, _logging.INFO),
        "warning": warning,
        "warn": warning,
        "error": _Level(target, _logging.ERROR),
        "critical": _Level(target, _logging.CRITICAL),
        "exception": _Level(target, _logging.ERROR, exc_info=True),
    }


_module_levels = _levels(_gway_logger)
debug = _module_levels["debug"]
info = _module_levels["info"]
warning = _module_levels["warning"]
warn = warning
error = _module_levels["error"]
critical = _module_levels["critical"]
exception = _module_levels["exception"]

debug.__doc__ = "Log a DEBUG diagnostic when that level is enabled."
info.__doc__ = "Log an INFO diagnostic when that level is enabled."
warning.__doc__ = "Log a WARNING diagnostic when that level is enabled."
warn.__doc__ = warning.__doc__
error.__doc__ = "Log an ERROR diagnostic when that level is enabled."
critical.__doc__ = "Log a CRITICAL diagnostic when that level is enabled."
exception.__doc__ = (
    "Log an ERROR diagnostic with the current exception traceback."
)


def __main__(message, *args, level=_logging.INFO, **kwargs):
    """Log one message through the Gway logger.

    Args:
        message: Logging format string or message object.
        level: Logging level name or numeric value; defaults to INFO.
    """
    return _gway_logger.log(_coerce_level(level), message, *args, **kwargs)


def config(level=None, logger=None):
    """Inspect or configure one Python logger.

    Args:
        level: Logging threshold name or numeric value to apply. When omitted, configuration is only inspected.
        logger: Logger name to target. When omitted, configure the parent Gway logger.
    """
    target = _logging.getLogger(logger) if logger else _gway_logger
    if level is not None:
        target.setLevel(_coerce_level(level))
    return {
        "logger": target.name or "root",
        "level": _logging.getLevelName(target.level),
        "effective_level": _logging.getLevelName(target.getEffectiveLevel()),
        "propagate": target.propagate,
        "handlers": len(target.handlers),
    }


def _child(name="gw", level=None):
    """Return a unique logger below the parent GWAY logger."""
    child = _gway_logger.getChild(f"{name}.{next(_instances)}")
    if level is not None:
        child.setLevel(_coerce_level(level))
    return child
