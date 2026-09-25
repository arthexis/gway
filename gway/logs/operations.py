"""Public logging operation orchestration over discovered sources and readers."""

from ..install.paths import install_paths
from ..install.service import ServiceInstallState
from .catalog import resolve_sources, source_catalog
from .file import read_file_logs
from .journal import read_journal
from .source import LogSource


_DEFAULT_QUERY_LIMIT = 100


class UnsupportedLogBackend(RuntimeError):
    """Raised when a selected source has no structured reader on this host."""

    def __init__(self, source):
        super().__init__(
            f"Log source {source.identity!r} uses unsupported read backend "
            f"{source.backend!r}"
        )
        self.source = source


class _CombinedInstallState:
    """Read service-install records from user and system scopes."""

    def __init__(self, states):
        self.states = tuple(states)

    def all(self):
        records = []
        for state in self.states:
            try:
                records.extend(state.all())
            except OSError:
                # An inaccessible system state must not hide the user's own
                # log namespace. Explicit inaccessible sources simply will not
                # be discoverable in this invocation.
                continue
        return records


def _install_state():
    states = []
    for system in (False, True):
        paths = install_paths(system=system)
        states.append(ServiceInstallState(paths.root / "services-installed"))
    return _CombinedInstallState(states)


def _catalog():
    return source_catalog(_install_state())


def _source_dict(source):
    return {
        "identity": source.identity,
        "kind": source.kind,
        "project": source.project,
        "service": source.service,
        "backend": source.backend,
        "backend_id": source.backend_id,
        "system": source.system,
    }


def _record_dict(record):
    return {
        "timestamp": record.timestamp.isoformat(),
        "source": record.source,
        "level": record.level,
        "message": record.message,
        "pid": record.pid,
        "unit": record.unit,
    }


def sources():
    """Return the selectable local GWAY log-source catalog."""
    return [_source_dict(source) for source in _catalog()]


def _journal_available():
    from .. import log as gway_log

    return gway_log._journal_address() is not None


def _file_paths(sources):
    from .. import log as gway_log

    paths = set()
    for source in sources:
        scopes = (source.system,) if source.system is not None else (False, True)
        for system in scopes:
            paths.add(gway_log.default_log_path(system=system))
    return sorted(paths, key=str)


def _query_groups(requested):
    catalog = _catalog()
    requested = tuple(requested)
    resolved = resolve_sources(requested, catalog)
    journal = []
    files = []

    for source in resolved:
        if source.backend == "systemd":
            journal.append(source)
        elif source.backend == "journal":
            if _journal_available():
                journal.append(source)
            else:
                files.append(source)
        elif source.backend == "process":
            if _journal_available():
                journal.append(
                    LogSource(
                        identity=source.identity,
                        kind=source.kind,
                        project=source.project,
                        service=source.service,
                        backend="journal",
                        backend_id=source.identity,
                        system=source.system,
                    )
                )
            else:
                files.append(source)
        elif requested and source.identity in set(requested):
            raise UnsupportedLogBackend(source)

    return journal, files


def _read(
    requested,
    *,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
):
    journal_sources, file_sources = _query_groups(requested)
    records = []

    if journal_sources:
        records.extend(
            read_journal(
                journal_sources,
                since=since,
                until=until,
                limit=limit,
                grep=grep,
                reverse=reverse,
            )
        )
    if file_sources:
        records.extend(
            read_file_logs(
                file_sources,
                paths=_file_paths(file_sources),
                since=since,
                until=until,
                limit=limit,
                grep=grep,
                reverse=reverse,
            )
        )

    records.sort(key=lambda record: record.timestamp, reverse=reverse)
    if limit is not None:
        limit = int(limit)
        records = records[:limit] if reverse else records[-limit:]
    return [_record_dict(record) for record in records]


def _selection(source, *, all=False):
    requested = tuple(source)
    if all and requested:
        raise ValueError("explicit log sources cannot be combined with --all")
    if not requested and not all:
        return None
    return requested


def read(*source, since=None, until=None, limit=_DEFAULT_QUERY_LIMIT, all=False):
    """Read bounded records from one or many managed log sources.

    With no source and without all=True, return the available source catalog
    instead of reading logs.
    """
    requested = _selection(source, all=all)
    if requested is None:
        return sources()
    return _read(requested, since=since, until=until, limit=limit)


def tail(*source, since=None, limit=_DEFAULT_QUERY_LIMIT, all=False):
    """Return the newest records from selected managed log sources.

    With no source and without all=True, return the available source catalog
    instead of reading logs.
    """
    requested = _selection(source, all=all)
    if requested is None:
        return sources()
    return _read(requested, since=since, limit=limit, reverse=True)


def search(
    pattern,
    *source,
    since=None,
    until=None,
    limit=_DEFAULT_QUERY_LIMIT,
    all=False,
):
    """Search selected managed log sources using the backend's native regex search.

    With no source and without all=True, return the available source catalog
    instead of reading logs.
    """
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("log search pattern cannot be empty")
    requested = _selection(source, all=all)
    if requested is None:
        return sources()
    return _read(
        requested,
        since=since,
        until=until,
        limit=limit,
        grep=pattern,
    )
