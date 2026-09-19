"""Source-agnostic primitives for GWAY ingestion."""

from dataclasses import dataclass, field
from types import MappingProxyType


def normalize_path(path):
    """Return an ingestion path as a non-empty tuple of string segments."""
    if isinstance(path, str):
        parts = tuple(part for part in path.replace("/", ".").split(".") if part)
    else:
        parts = tuple(str(part) for part in path if str(part))

    if not parts:
        raise ValueError("Ingested operation path cannot be empty")
    return parts


def canonical_name(path):
    """Return the dotted canonical name for an ingestion path."""
    return ".".join(normalize_path(path))


@dataclass
class IngestedObject:
    """Gateway-local state for one object encountered during ingestion."""

    value: object
    paths: set[tuple[str, ...]] = field(default_factory=set)
    registered: bool = False
    operation: object = None
    expanded: bool = False
    expander: object = None


def remember_object(gateway, value, path, *, expander=None):
    """Remember an object by identity and record another path that reaches it."""
    path = normalize_path(path)
    state = gateway._ingested
    identity = id(value)
    record = state.get(identity)
    if record is None:
        record = IngestedObject(value=value, expander=expander)
        state[identity] = record
    elif record.expander is None and expander is not None:
        record.expander = expander
    record.paths.add(path)
    return record


def find_ingested(gateway, path):
    """Return the remembered object reachable at an exact ingestion path."""
    path = normalize_path(path)
    for record in gateway._ingested.values():
        if path in record.paths:
            return record
    return None


def expand_path(gateway, path):
    """Expand one known but unexpanded ingestion path, if possible."""
    path = normalize_path(path)
    record = find_ingested(gateway, path)
    if record is None or record.expanded or not callable(record.expander):
        return False
    record.expander(gateway, record.value, path=path)
    return True


@dataclass(frozen=True)
class IngestedOperation:
    """Description of one callable discovered by an ingestor."""

    path: tuple[str, ...]
    callable: object
    source: object = None
    kind: str | None = None
    aliases: tuple[str, ...] = ()
    metadata: object = field(default_factory=dict)

    def __post_init__(self):
        path = normalize_path(self.path)
        if not callable(self.callable):
            raise TypeError(f"{canonical_name(path)!r} is not callable")

        object.__setattr__(self, "path", path)
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def name(self):
        return canonical_name(self.path)


def register_operation(gateway, operation):
    """Wrap and register one discovered callable on a Gateway."""
    if not isinstance(operation, IngestedOperation):
        raise TypeError("operation must be an IngestedOperation")

    wrapped = gateway.wrap(operation.name, operation.callable)
    wrapped.__gway_source__ = operation.source
    wrapped.__gway_source_kind__ = operation.kind
    wrapped.__gway_path__ = operation.path
    wrapped.__gway_metadata__ = operation.metadata

    for alias in operation.aliases:
        gateway.ops.register_alias(alias, wrapped)

    return wrapped


def register_operations(gateway, operations):
    """Register a sequence of discovered operations and return the wrapped callables."""
    return [register_operation(gateway, operation) for operation in operations]
