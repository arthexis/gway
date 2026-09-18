"""Semantic registry views for executable GWAY operations."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationRecord:
    """One executable operation and its semantic subject."""

    name: str
    op: str
    sub: str | None
    callable: object


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

    def register(self, name, operation):
        if not callable(operation):
            raise TypeError(f"{name!r} is not callable")
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

    def resolve(self, name, default=None):
        canonical = self.aliases.get(name, name)
        record = self.records.get(canonical)
        return record.callable if record is not None else default

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

    def register(self, name, operation):
        return self._registry.register(name, operation)

    def register_alias(self, name, operation):
        return self._registry.alias(name, operation)

    def unregister(self, name):
        return self._registry.unregister(name)

    def resolve(self, name, default=None):
        return self._registry.resolve(name, default)

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
        return iter(dict.fromkeys(record.op for record in self._registry.records.values()))

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
