"""Built-in logging operations and GWAY logger hierarchy."""

from contextlib import contextmanager as _contextmanager
from contextvars import ContextVar as _ContextVar
from itertools import count as _count
import json as _json
import logging as _logging
from logging.handlers import TimedRotatingFileHandler as _TimedRotatingFileHandler
from pathlib import Path as _Path
import os as _os
import socket as _socket
import sys as _sys
from datetime import datetime as _datetime, timezone as _timezone

from .environment import environment_value as _environment_value


_DEFAULT_LEVEL = _logging.WARNING
_DEFAULT_OUTPUT_LEVEL = _logging.INFO
_DEFAULT_LOG_FILENAME = "gway.log"
_LOG_RETENTION_DAYS = 30
_LOG_BACKUP_COUNT = _LOG_RETENTION_DAYS - 1
_JOURNAL_ADDRESSES = (
    "/run/systemd/journal/dev-log",
    "/dev/log",
)
_SYSLOG_USER_FACILITY = 1
_gway_logger = _logging.getLogger("gway")
_gway_logger.setLevel(_DEFAULT_LEVEL)
logger = _gway_logger
_instances = _count()
_output_handler = None
_log_source = _ContextVar(
    "gway_log_source",
    default=_environment_value("GWAY_LOG_SOURCE", "gway"),
)


def _current_source():
    """Return the logical log source for the current execution context."""
    return _log_source.get()


def _validate_source(identity):
    value = str(identity).strip()
    if not value:
        raise ValueError("log source identity cannot be empty")
    if "\n" in value or "\r" in value or ":" in value:
        raise ValueError("log source identity contains invalid syslog characters")
    return value


@_contextmanager
def _source_scope(identity):
    """Temporarily assign a logical source to GWAY diagnostics."""
    token = _log_source.set(_validate_source(identity))
    try:
        yield _current_source()
    finally:
        _log_source.reset(token)


class _SourceFilter(_logging.Filter):
    """Attach the current logical GWAY source to every emitted record."""

    def filter(self, record):
        record.gway_source = _current_source()
        return True


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
    """Return the durable rotating-file GWAY log path without creating it."""
    if root is None:
        from .install.paths import data_root

        root = data_root(system=system, **kwargs)
    return _Path(root).expanduser() / "logs" / _DEFAULT_LOG_FILENAME


def _journal_address():
    """Return the first local journald-compatible syslog socket, if present."""
    for address in _JOURNAL_ADDRESSES:
        if _os.path.exists(address):
            return address
    return None


def default_output_destination():
    """Return GWAY's default diagnostic destination for this host."""
    return "journal" if _journal_address() is not None else "file"


def _journal_priority(level):
    """Map a Python logging level to syslog/journal priority."""
    if level >= _logging.CRITICAL:
        return 2
    if level >= _logging.ERROR:
        return 3
    if level >= _logging.WARNING:
        return 4
    if level >= _logging.INFO:
        return 6
    return 7


class _JsonLogFormatter(_logging.Formatter):
    """Render one portable durable log record as JSON Lines."""

    def format(self, record):
        source = getattr(record, "gway_source", _current_source())
        payload = {
            "timestamp": _datetime.fromtimestamp(
                record.created,
                tz=_timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "source": source,
            "message": record.getMessage(),
            "pid": record.process,
            "unit": None,
        }
        return _json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _JournalHandler(_logging.Handler):
    """Send GWAY records to journald through its local syslog socket."""

    def __init__(self, address):
        super().__init__()
        self.address = address
        self._socket = None

    def _connect(self):
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_DGRAM)
        sock.connect(self.address)
        self._socket = sock
        return sock

    def _send(self, payload):
        sock = self._socket or self._connect()
        try:
            sock.send(payload)
        except OSError:
            try:
                sock.close()
            finally:
                self._socket = None
            raise

    def emit(self, record):
        message = self.format(record)
        priority = (_SYSLOG_USER_FACILITY * 8) + _journal_priority(record.levelno)
        identifier = getattr(record, "gway_source", _current_source())
        payload = f"<{priority}>{identifier}: {message}".encode(
            "utf-8",
            errors="replace",
        )
        try:
            self._send(payload)
        except OSError:
            # Logging must never make the GWAY operation fail merely because
            # the host journal is temporarily unavailable.
            try:
                _sys.stderr.write(message + "\n")
                _sys.stderr.flush()
            except Exception:
                self.handleError(record)

    def close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
        super().close()


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
    destination=None,
    level=_DEFAULT_OUTPUT_LEVEL,
    system=False,
    root=None,
    formatter=None,
):
    """Configure GWAY's global diagnostic destination."""
    global _output_handler

    numeric_level = _coerce_level(level)
    if destination is None:
        destination = default_output_destination()

    _remove_output_handler()

    journal = False
    durable_file = False
    if isinstance(destination, _Path):
        handler = _daily_file_handler(destination.expanduser())
        durable_file = True
    else:
        selected = str(destination).strip()
        lowered = selected.lower()
        if lowered == "journal":
            address = _journal_address()
            if address is None:
                handler = _logging.StreamHandler(_sys.stderr)
            else:
                handler = _JournalHandler(address)
                journal = True
        elif lowered == "file":
            handler = _daily_file_handler(default_log_path(system=system, root=root))
            durable_file = True
        elif lowered == "stdout":
            handler = _logging.StreamHandler(_sys.stdout)
        elif lowered == "stderr":
            handler = _logging.StreamHandler(_sys.stderr)
        else:
            handler = _daily_file_handler(_Path(selected).expanduser())
            durable_file = True

    handler.setLevel(numeric_level)
    handler.addFilter(_SourceFilter())
    handler.setFormatter(
        formatter
        or (
            _JsonLogFormatter()
            if durable_file
            else _logging.Formatter(
                "%(message)s"
                if journal
                else "%(asctime)s %(levelname)s %(name)s [%(gway_source)s] %(message)s"
            )
        )
    )
    handler._gway_output_handler = True
    _gway_logger.addHandler(handler)
    _gway_logger.setLevel(numeric_level)
    _gway_logger.propagate = False
    _output_handler = handler
    return handler


@_contextmanager
def output_scope(**kwargs):
    """Temporarily configure GWAY output while preserving embedded logger state."""
    global _output_handler

    previous_handler = _output_handler
    previous_level = _gway_logger.level
    previous_propagate = _gway_logger.propagate

    if previous_handler is not None:
        _gway_logger.removeHandler(previous_handler)
        _output_handler = None

    try:
        configure_output(**kwargs)
        yield _output_handler
    finally:
        _remove_output_handler()
        _gway_logger.setLevel(previous_level)
        _gway_logger.propagate = previous_propagate
        if previous_handler is not None:
            _gway_logger.addHandler(previous_handler)
            _output_handler = previous_handler


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



def sources():
    """List selectable GWAY-managed log sources."""
    from .logs.operations import sources as _sources

    return _sources()


def read(
    *source: str,
    since: str = None,
    until: str = None,
    limit: int = None,
):
    """Read bounded records from GWAY-managed log sources."""
    from .logs.operations import read as _read

    return _read(*source, since=since, until=until, limit=limit)


def tail(
    *source: str,
    since: str = None,
    limit: int = 100,
):
    """Return the newest records from GWAY-managed log sources."""
    from .logs.operations import tail as _tail

    return _tail(*source, since=since, limit=limit)


def search(
    pattern: str,
    *source: str,
    since: str = None,
    until: str = None,
    limit: int = None,
):
    """Search message content in GWAY-managed log sources."""
    from .logs.operations import search as _search

    return _search(
        pattern,
        *source,
        since=since,
        until=until,
        limit=limit,
    )
