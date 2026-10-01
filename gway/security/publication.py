"""Normalized security-scope publications from projects and ingesters."""

from dataclasses import dataclass
from collections.abc import Iterable, Mapping


def _strings(values, *, lower=False):
    normalized = []
    for value in values or ():
        value = str(value).strip()
        if not value:
            continue
        normalized.append(value.lower() if lower else value)
    return frozenset(normalized)


@dataclass(frozen=True)
class PublishedScope:
    """One normalized scope proposal produced by an external publisher.

    Publishers describe desired authority and provenance only. They never write
    directly to the security database; validation and durable convergence stay
    centralized in Gway's security layer.
    """

    name: str
    source: str
    operations: frozenset[str] = frozenset()
    environment: frozenset[str] = frozenset()
    semantic_terms: frozenset[str] = frozenset()

    def __post_init__(self):
        name = str(self.name).strip()
        source = str(self.source or "").strip()
        if not name:
            raise ValueError("published scope names must be non-empty strings")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "operations", _strings(self.operations))
        object.__setattr__(self, "environment", _strings(self.environment))
        object.__setattr__(
            self,
            "semantic_terms",
            _strings(self.semantic_terms, lower=True),
        )

    @classmethod
    def from_definition(cls, name, definition):
        """Normalize a legacy/project mapping into one publication."""
        if isinstance(definition, cls):
            if str(name).strip() != definition.name:
                raise ValueError(
                    f"Published scope key {name!r} does not match {definition.name!r}"
                )
            return definition
        if not isinstance(definition, Mapping):
            raise TypeError(f"Published scope {name!r} must be a mapping or PublishedScope")
        return cls(
            name=name,
            source=definition.get("source") or "",
            operations=definition.get("operations", ()),
            environment=definition.get("environment", ()),
            semantic_terms=definition.get("semantic_terms", ()),
        )

    @property
    def owner(self):
        """Return the durable registry owner for this publisher."""
        if not self.source:
            raise ValueError(f"Published security scope {self.name} has no publisher source")
        return f"project:{self.source}"

    def as_definition(self):
        """Return the compatibility mapping used by existing callers."""
        return {
            "source": self.source,
            "operations": self.operations,
            "environment": self.environment,
            "semantic_terms": self.semantic_terms,
        }


def normalize_publications(publications):
    """Return a deterministic name->PublishedScope mapping from any publisher.

    Existing ``pyproject.toml`` publication dictionaries are accepted as a
    compatibility adapter. Ingester publishers can emit ``PublishedScope``
    objects directly without knowing anything about registry persistence.
    """
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
