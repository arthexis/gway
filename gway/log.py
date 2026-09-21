"""Built-in logging operations and GWAY logger hierarchy."""

from itertools import count as _count
import logging as _logging
from logging.handlers import TimedRotatingFileHandler as _TimedRotatingFileHandler
from pathlib import Path as _Path
import sys as _sys


_DEFAULT_LEVEL = _logging.WARNING
_DEFAULT_OUTPUT_LEVEL = _logging.INFO
_DEFAULT_LOG_FILENAME = "gway.log"
_LOG_RETENTION_DAYS = 30
_LOG_BACKUP_COUNT = _LOG_RETENTION_DAYS - 1
_gway_logger = _logging.getLogger("gway")
_gway_logger.setLevel(_DEFAULT_LEVEL)
logger = _gway_logger
_instances = _count()
_output_handler = None


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


def default_log_path(*, system=False, root=None, **kwargs):
    """Return the durable GWAY log path without creating it."""
    if root is None:
        from .install.paths import data_root

        root = data_root(system=system, **kwargs)
    return _Path(root).expanduser() / "logs" / _DEFAULT_LOG_FILENAME


def _remove_output_handler():
    """Detach and close the GWAY-managed persistent or stream handler."""
    global _output_handler
    if _output_handler is None:
        return
    _gway_logger.removeHandler(_output_handler)
    _output_handler.close()
    _output_handler = None


def _daily_file_handler(path):
    """Return a daily rotating log handler with 30 dated backups."""
    path = _Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = _TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.suffix = "%Y-%m-%d"
    return handler


def configure_output(
    *,
    destination="file",
    level=_DEFAULT_OUTPUT_LEVEL,
    system=False,
    root=None,
    formatter=None,
):
    """Configure GWAY's global log destination."""
    global _output_handler

    numeric_level = _coerce_level(level)
    if destination is None:
        destination = "file"

    _remove_output_handler()

    if isinstance(destination, _Path):
        handler = _daily_file_handler(destination.expanduser())
    else:
        selected = str(destination).strip()
        lowered = selected.lower()
        if lowered == "file":
            handler = _daily_file_handler(
                default_log_path(system=system, root=root)
            )
        elif lowered == "stdout":
            handler = _logging.StreamHandler(_sys.stdout)
        elif lowered == "stderr":
            handler = _logging.StreamHandler(_sys.stderr)
        else:
            handler = _daily_file_handler(_Path(selected).expanduser())

    handler.setLevel(numeric_level)
    handler.setFormatter(
        formatter
        or _logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    handler._gway_output_handler = True
    _gway_logger.addHandler(handler)
    _gway_logger.setLevel(numeric_level)
    _gway_logger.propagate = False
    _output_handler = handler
    return handler


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
exception.__doc__ = "Log an ERROR diagnostic with the current exception traceback."


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
