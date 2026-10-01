"""Pure semantic relationships for security scopes.

Semantic authority is intentionally inverted relative to term-set size: a scope
with fewer terms is broader because it matches more concrete leaves. These
helpers operate only on explicit ``Scope.semantic_terms`` metadata; scope names
are never parsed for meaning.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticResolution:
    """Concrete semantic leaves and effective operations for requested terms.

    ``exact_scopes`` names existing scopes whose semantic identity exactly
    matches the requested terms. When none exists, ``conjunction`` is a
    deterministic minimal set of existing broader scopes whose semantic terms
    combine to the requested identity. The conjunction is descriptive only:
    authorization always evaluates the original combined term set, so it can
    never accidentally turn an AND requirement into independent OR grants.
    """

    terms: frozenset[str]
    scopes: tuple[str, ...] = ()
    operations: frozenset[str] = frozenset()
    exact_scopes: tuple[str, ...] = ()
    conjunction: tuple[str, ...] = ()


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
            (
                scope
                for scope in scopes
                if scope.semantic_terms and requested <= scope.semantic_terms
            ),
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
            raise ValueError(f"Security scope {scope.name} has no semantic terms")
    common = set(scopes[0].semantic_terms)
    for scope in scopes[1:]:
        common.intersection_update(scope.semantic_terms)
    if not common:
        raise ValueError(
            "semantic union has no common terms; empty semantic authority is not allowed"
        )
    return frozenset(common)


def _conjunctive_cover(scopes, requested):
    """Return a deterministic minimal AND decomposition for requested terms.

    Each component is broader than the requested authority on its own. Their
    semantic requirements are combined conjunctively, so a matching leaf must
    satisfy every component. Only the representation is decomposed; the stored
    and authorized union scope remains the original requested term set.
    """
    representatives = {}
    for scope in scopes:
        scope_terms = frozenset(scope.semantic_terms)
        if not scope_terms or scope_terms == requested or not scope_terms < requested:
            continue
        existing = representatives.get(scope_terms)
        if existing is None or scope.name < existing:
            representatives[scope_terms] = scope.name

    # Dynamic programming over covered requested terms finds the smallest
    # conjunctive cover without exponential combinations of equivalent scopes.
    best = {frozenset(): ()}
    for scope_terms, name in sorted(
        representatives.items(), key=lambda item: (item[1], sorted(item[0]))
    ):
        pending = dict(best)
        for covered, names in best.items():
            combined = covered | scope_terms
            candidate = tuple(sorted((*names, name)))
            current = pending.get(combined)
            if current is None or (len(candidate), candidate) < (
                len(current),
                current,
            ):
                pending[combined] = candidate
        best = pending
    return best.get(requested, ())


def resolve(scopes, requested):
    """Resolve semantic terms to representation, matching leaves, and operations.

    Environment grants are deliberately excluded from semantic aggregation.
    Existing scopes with exactly the requested semantic identity are preferred
    as the canonical representation. If no exact scope exists, a conjunctive
    decomposition may be reported, but authorization still matches the complete
    requested term set directly.
    """
    requested = terms(requested)
    scopes = tuple(scopes)
    matched = match(scopes, requested)
    operations = frozenset(
        operation for scope in matched for operation in scope.operations
    )
    exact_scopes = tuple(
        sorted(scope.name for scope in scopes if scope.semantic_terms == requested)
    )
    conjunction = () if exact_scopes else _conjunctive_cover(scopes, requested)
    return SemanticResolution(
        terms=requested,
        scopes=tuple(scope.name for scope in matched),
        operations=operations,
        exact_scopes=exact_scopes,
        conjunction=conjunction,
    )
