"""Build and resolve the logical GWAY log-source namespace."""

from .discovery import installed_sources
from .identity import gway_identity
from .source import LogSource


class UnknownLogSource(ValueError):
    """Raised when a requested logical log source is not known."""

    def __init__(self, identity):
        super().__init__(f"Unknown log source: {identity}")
        self.identity = identity


def source_catalog(state):
    """Return all selectable logical log sources known to GWAY.

    The built-in gway identity is reserved for GWAY's own journal records.
    If service-install state contains a project also named gway, its concrete
    services remain selectable as gway/<service> but the conflicting project
    aggregate is omitted.
    """
    builtin = LogSource(
        identity=gway_identity(),
        kind="gway",
        backend="journal",
        backend_id=gway_identity(),
    )
    discovered = installed_sources(state)
    return [
        builtin,
        *[
            source
            for source in discovered
            if not (
                source.kind == "project"
                and source.identity == builtin.identity
            )
        ],
    ]


def _catalog_index(available):
    index = {}
    for source in available:
        previous = index.get(source.identity)
        if previous is not None and previous != source:
            raise ValueError(
                f"Duplicate log source identity: {source.identity}"
            )
        index[source.identity] = source
    return index


def _project_members(project, available):
    return [
        source
        for source in available
        if source.kind != "project"
        and source.project == project
    ]


def resolve_sources(requested, available):
    """Expand logical selections into unique concrete log sources.

    An empty request selects every concrete GWAY-managed source. Project
    sources expand by project metadata rather than identity-prefix matching.
    """
    available = list(available)
    index = _catalog_index(available)
    requested = list(requested or ())

    if not requested:
        selected = [
            source
            for source in available
            if source.kind != "project"
        ]
    else:
        selected = []
        for identity in requested:
            source = index.get(identity)
            if source is None:
                raise UnknownLogSource(identity)
            if source.kind == "project":
                selected.extend(_project_members(source.project, available))
            else:
                selected.append(source)

    unique = {}
    for source in selected:
        unique[source.identity] = source
    return [unique[identity] for identity in sorted(unique)]
