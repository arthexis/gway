"""Semantic registry views for executable GWAY operations."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


_INVERSE_VERBS = {
    "create": "delete",
    "delete": "create",
    "install": "uninstall",
    "uninstall": "install",
    "start": "stop",
    "stop": "start",
    "link": "remove",
    "redirect": "remove",
}


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


def _command_words(name):
    """Normalize public command spellings without rewriting special identities."""
    words = []
    for raw in str(name).replace(".", " ").split():
        if raw.startswith("__") and raw.endswith("__"):
            words.append(raw)
            continue
        if raw == "-" or raw.startswith("--"):
            words.append(raw)
            continue
        for part in raw.replace("_", " ").split():
            words.extend(piece for piece in part.replace("-", " ").split() if piece)
    return tuple(words)


class _Registry:
    def __init__(self):
        self.records = {}
        self.aliases = {}
        self.history = {}

    def register(self, name, operation, *, op=None, sub=None):
        if not callable(operation):
            raise TypeError(f"{name!r} is not callable")
        if op is None:
            op, sub = split_operation(name)
        previous = self.records.get(name)
        if previous is not None and previous.callable is not operation:
            self.history.setdefault(name, []).append(previous)
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

        requested_words = _command_words(name)
        spelling_matches = {}
        for identity, target in self.aliases.items():
            if _command_words(identity) != requested_words:
                continue
            matched = self.records.get(target)
            if matched is not None:
                spelling_matches[target] = matched
        for identity, matched in self.records.items():
            if _command_words(identity) == requested_words:
                spelling_matches[identity] = matched
        if len(spelling_matches) == 1:
            return next(iter(spelling_matches.values())).callable

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

    def candidates(self, name):
        """Return selected then shadowed records for one canonical identity."""
        canonical = self.aliases.get(name, name)
        selected = self.records.get(canonical)
        if selected is None:
            return ()
        shadowed = reversed(self.history.get(canonical, ()))
        return (selected, *shadowed)

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

    def candidates(self, name):
        """Return selected then shadowed registrations in resolver precedence."""
        return self._registry.candidates(name)

    def canonical_name(self, operation, default=None):
        """Return the canonical registry identity for one operation callable."""
        for name, record in self._registry.records.items():
            if record.callable is operation:
                return name
        return default

    def children(self, prefix):
        """Return immediate child operations below one namespace, including aliases."""
        parts = tuple(
            part for part in str(prefix).replace(" ", ".").split(".") if part
        )
        if not parts:
            return ()
        dotted = ".".join(parts)
        found = {}

        def include(name, operation):
            if not name.startswith(f"{dotted}."):
                return
            remainder = name[len(dotted) + 1 :]
            child, separator, _ = remainder.partition(".")
            if separator:
                found.setdefault(child, None)
            else:
                found[child] = operation

        for name, record in self._registry.records.items():
            include(name, record.callable)

        for alias, canonical in self._registry.aliases.items():
            record = self._registry.records.get(canonical)
            if record is not None:
                include(alias, record.callable)

        return tuple((name, found[name]) for name in sorted(found))

    def is_namespace(self, prefix):
        """Return whether an operation prefix has registered children."""
        return bool(self.children(prefix))

    def records(self):
        """Return the live canonical operation records in registration order."""
        return tuple(self._registry.records.values())

    def rollback_operation(self, operation, default=None):
        """Resolve the semantic inverse operation for a registered callable.

        An explicit __gway_rollback__ operation identity wins. Otherwise,
        conventional inverse verbs are resolved on the same semantic subject.
        """
        canonical = self.canonical_name(operation)
        if canonical is None:
            return default
        record = self._registry.records.get(canonical)
        if record is None:
            return default

        explicit = getattr(record.callable, "__gway_rollback__", None)
        if explicit:
            if callable(explicit):
                return explicit
            resolved = self.resolve(str(explicit))
            return resolved if resolved is not None else default

        inverse = _INVERSE_VERBS.get(record.op)
        if inverse is None or record.sub is None:
            return default
        return self.resolve_pair(inverse, record.sub, default)

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
