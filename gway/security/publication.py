"""Normalized curated security-scope publications from projects."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def _strings(values):
    normalized = []
    for value in values or ():
        value = str(value).strip()
        if value:
            normalized.append(value)
    return frozenset(normalized)


@dataclass(frozen=True)
class PublishedScope:
    """One explicitly curated scope proposal produced by an external publisher."""

    name: str
    source: str
    operations: frozenset[str] = frozenset()
    environment: frozenset[str] = frozenset()

    def __post_init__(self):
        name = str(self.name).strip()
        source = str(self.source or "").strip()
        if not name:
            raise ValueError("published scope names must be non-empty strings")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "operations", _strings(self.operations))
        object.__setattr__(self, "environment", _strings(self.environment))

    @classmethod
    def from_definition(cls, name, definition):
        if isinstance(definition, cls):
            if str(name).strip() != definition.name:
                raise ValueError(
                    f"Published scope key {name!r} does not match {definition.name!r}"
                )
            return definition
        if not isinstance(definition, Mapping):
            raise TypeError(
                f"Published scope {name!r} must be a mapping or PublishedScope"
            )
        unknown = set(definition) - {"source", "operations", "environment"}
        if unknown:
            raise ValueError(
                f"Unknown published scope fields for {name}: "
                + ", ".join(sorted(unknown))
            )
        return cls(
            name=name,
            source=definition.get("source") or "",
            operations=definition.get("operations", ()),
            environment=definition.get("environment", ()),
        )

    @property
    def owner(self):
        if not self.source:
            raise ValueError(
                f"Published security scope {self.name} has no publisher source"
            )
        return f"project:{self.source}"

    def as_definition(self):
        return {
            "source": self.source,
            "operations": self.operations,
            "environment": self.environment,
        }


def normalize_publications(publications):
    """Return a deterministic name->PublishedScope mapping."""
    if publications is None:
        return {}
    if isinstance(publications, Mapping):
        items = publications.items()
    else:
        if not isinstance(publications, Iterable):
            raise TypeError("scope publications must be a mapping or iterable")
        items = ((publication.name, publication) for publication in publications)

    normalized = {}
    for name, definition in items:
        publication = PublishedScope.from_definition(name, definition)
        existing = normalized.get(publication.name)
        if existing is not None and existing != publication:
            raise ValueError(f"Conflicting publications for scope {publication.name}")
        normalized[publication.name] = publication
    return dict(sorted(normalized.items()))
