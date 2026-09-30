"""Pure semantic relationships for security scopes.

Semantic authority is intentionally inverted relative to term-set size: a scope
with fewer terms is broader because it matches more concrete leaves.  These
helpers operate only on explicit ``Scope.semantic_terms`` metadata; scope names
are never parsed for meaning.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticResolution:
    """Concrete semantic leaves and effective operations for requested terms."""

    terms: frozenset[str]
    scopes: tuple[str, ...] = ()
    operations: frozenset[str] = frozenset()


def terms(values):
    """Return canonical semantic terms and reject an empty semantic request."""
    normalized = frozenset(str(value).strip().lower() for value in values)
    if "" in normalized:
        raise ValueError("semantic terms must be non-empty strings")
    if not normalized:
        raise ValueError("semantic scope requires at least one term")
    return normalized


def contains(scope, requested):
    """Return whether one explicit semantic leaf contains requested authority."""
    requested = terms(requested)
    return bool(scope.semantic_terms) and requested <= scope.semantic_terms


def match(scopes, requested):
    """Return semantic leaves matching requested terms in stable name order."""
    requested = terms(requested)
    return tuple(
        sorted(
            (scope for scope in scopes if scope.semantic_terms and requested <= scope.semantic_terms),
            key=lambda scope: scope.name,
        )
    )


def union(scopes):
    """Return the least broad semantic authority containing all supplied scopes.

    Because fewer terms confer broader semantic authority, this authority-union
    is represented by the intersection of the supplied term sets.
    """
    scopes = tuple(scopes)
    if not scopes:
        raise ValueError("semantic union requires at least one scope")
    for scope in scopes:
        if not scope.semantic_terms:
            raise ValueError(
                f"Security scope {scope.name} has no semantic terms"
            )
    common = set(scopes[0].semantic_terms)
    for scope in scopes[1:]:
        common.intersection_update(scope.semantic_terms)
    if not common:
        raise ValueError(
            "semantic union has no common terms; empty semantic authority is not allowed"
        )
    return frozenset(common)


def resolve(scopes, requested):
    """Resolve semantic terms to matching leaf names and operation authority.

    Environment grants are deliberately excluded from semantic aggregation.
    """
    requested = terms(requested)
    matched = match(scopes, requested)
    operations = frozenset(
        operation
        for scope in matched
        for operation in scope.operations
    )
    return SemanticResolution(
        terms=requested,
        scopes=tuple(scope.name for scope in matched),
        operations=operations,
    )
