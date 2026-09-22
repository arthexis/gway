"""Public logging operation orchestration over discovered sources and readers."""

from dataclasses import asdict

from ..install.paths import install_paths
from ..install.service import ServiceInstallState
from .catalog import resolve_sources, source_catalog
from .journal import read_journal


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


def _resolved(requested):
    catalog = _catalog()
    requested = tuple(requested)
    resolved = resolve_sources(requested, catalog)
    if requested:
        unreadable = [
            source
            for source in resolved
            if source.backend not in {"systemd", "journal"}
        ]
        if unreadable:
            raise UnsupportedLogBackend(unreadable[0])
        return resolved

    # Until rotating-file structured reads are implemented, an empty request
    # means every currently readable managed source, never the whole host log.
    return [
        source
        for source in resolved
        if source.backend in {"systemd", "journal"}
    ]


def _read(
    requested,
    *,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
):
    selected = _resolved(requested)
    records = read_journal(
        selected,
        since=since,
        until=until,
        limit=limit,
        grep=grep,
        reverse=reverse,
    )
    return [_record_dict(record) for record in records]


def read(*source, since=None, until=None, limit=None):
    """Read bounded records from zero, one, or many managed log sources.

    Args:
        source: Logical source identities. Omit to read all currently readable
            GWAY-managed sources.
        since: Lower journal time bound accepted by the active reader.
        until: Upper journal time bound accepted by the active reader.
        limit: Maximum records to return.
    """
    return _read(source, since=since, until=until, limit=limit)


def tail(*source, since=None, limit=100):
    """Return the newest records from managed log sources.

    Args:
        source: Logical source identities. Omit for all readable managed
            sources.
        since: Optional lower journal time bound.
        limit: Maximum newest records to return. Defaults to 100.
    """
    return _read(source, since=since, limit=limit, reverse=True)


def search(pattern, *source, since=None, until=None, limit=None):
    """Search journal message content using the backend's native regex search.

    Args:
        pattern: Message regular expression forwarded to the journal backend.
        source: Logical source identities. Omit for all readable managed
            sources.
        since: Optional lower journal time bound.
        until: Optional upper journal time bound.
        limit: Maximum matching records to return.
    """
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("log search pattern cannot be empty")
    return _read(
        source,
        since=since,
        until=until,
        limit=limit,
        grep=pattern,
    )
