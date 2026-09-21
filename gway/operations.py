"""Semantic registry views for executable GWAY operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class OperationRecord:
    """One executable operation and its semantic subject."""

    name: str
    op: str
    sub: str | None
    callable: object


class Cardinality(str, Enum):
    """Requested semantic subject cardinality."""

    ONE = "one"
    MANY = "many"


def singularize(name):
    """Return the simple singular form used for semantic subject aliases."""
    if name.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if name.endswith(("xes", "zes", "ches", "shes", "ses")) and len(name) > 2:
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss") and len(name) > 1:
        return name[:-1]
    return None


def subject_cardinality(requested, canonical):
    """Return ONE/MANY when requested names the canonical semantic subject."""
    if requested == canonical:
        return Cardinality.ONE
    if singularize(requested) == canonical:
        return Cardinality.MANY
    return None


def split_operation(name):
    """Split a canonical operation name into operation and subject."""
    simple = name.rsplit(".", 1)[-1].replace("-", "_")
    words = simple.split("_")
    if len(words) > 1:
        return words[0], "_".join(words[1:])

    parts = name.split(".")
    if len(parts) > 1:
        return parts[-1], parts[-2]
    return simple, None


class _Registry:
    def __init__(self):
        self.records = {}
        self.aliases = {}

    def register(self, name, operation, *, op=None, sub=None):
        if not callable(operation):
            raise TypeError(f"{name!r} is not callable")
        if op is None:
            op, sub = split_operation(name)
        self.records[name] = OperationRecord(name, op, sub, operation)
        self.aliases[name] = name
        return operation

    def alias(self, name, operation):
        for canonical, record in self.records.items():
            if record.callable is operation:
                self.aliases[name] = canonical
                return operation
        return self.register(name, operation)

    def resolve_pair(self, op, sub, default=None):
        matches = [
            record.callable
            for record in self.records.values()
            if record.op == op and record.sub == sub
        ]
        if len(matches) == 1:
            return matches[0]
        return default

    def resolve(self, name, default=None):
        canonical = self.aliases.get(name, name)
        record = self.records.get(canonical)
        if record is not None:
            return record.callable

        parts = tuple(part for part in str(name).replace(" ", ".").split(".") if part)
        if len(parts) < 2:
            singular = singularize(parts[0]) if parts else None
            if singular is None:
                return default
            canonical = self.aliases.get(singular, singular)
            record = self.records.get(canonical)
            return record.callable if record is not None else default

        op, sub = parts[-2], parts[-1]
        matches = [
            record
            for record in self.records.values()
            if record.op == op and record.sub == sub
        ]
        if not matches:
            singular = singularize(sub)
            if singular is not None:
                matches = [
                    record
                    for record in self.records.values()
                    if record.op == op and record.sub == singular
                ]

        prefix = ".".join(parts[:-2])
        if prefix:
            matches = [
                record for record in matches if record.name.startswith(f"{prefix}.")
            ]

        if len(matches) == 1:
            return matches[0].callable
        return default

    def unregister(self, name):
        canonical = self.aliases.get(name, name)
        record = self.records.pop(canonical)
        stale = [alias for alias, target in self.aliases.items() if target == canonical]
        for alias in stale:
            del self.aliases[alias]
        return record.callable


class _Family(Mapping):
    def __init__(self, items):
        self._items = dict(items)

    def __getitem__(self, key):
        return self._items[key]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class Operations(Mapping):
    """Mapping of operation names to their subject/callable families."""

    def __init__(self, registry=None):
        self._registry = registry or _Registry()

    def register(self, name, operation, *, op=None, sub=None):
        return self._registry.register(name, operation, op=op, sub=sub)

    def register_alias(self, name, operation):
        return self._registry.alias(name, operation)

    def unregister(self, name):
        return self._registry.unregister(name)

    def resolve(self, name, default=None):
        return self._registry.resolve(name, default)

    def resolve_pair(self, op, sub, default=None):
        return self._registry.resolve_pair(op, sub, default)

    def __getitem__(self, op):
        items = {
            record.sub: record.callable
            for record in self._registry.records.values()
            if record.op == op
        }
        if not items:
            raise KeyError(op)
        return _Family(items)

    def __iter__(self):
        return iter(
            dict.fromkeys(record.op for record in self._registry.records.values())
        )

    def __len__(self):
        return len(set(record.op for record in self._registry.records.values()))


class Subjects(Mapping):
    """Mapping of subjects to their operation/callable families."""

    def __init__(self, registry=None):
        self._registry = registry or _Registry()

    def __getitem__(self, sub):
        items = {
            record.op: record.callable
            for record in self._registry.records.values()
            if record.sub == sub
        }
        if not items:
            raise KeyError(sub)
        return _Family(items)

    def __iter__(self):
        return iter(
            dict.fromkeys(
                record.sub
                for record in self._registry.records.values()
                if record.sub is not None
            )
        )

    def __len__(self):
        return len(
            {
                record.sub
                for record in self._registry.records.values()
                if record.sub is not None
            }
        )


def registry_views():
    """Create operation and subject views backed by one registry."""
    registry = _Registry()
    return Operations(registry), Subjects(registry)
