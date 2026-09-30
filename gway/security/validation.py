"""Safety validation for semantic security scopes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeValidation:
    """Validation result for one semantic scope."""

    name: str
    valid: bool
    mutating: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()


def validate_scope(gateway, scope):
    """Validate semantic read/write invariants for one scope.

    Legacy exact-only scopes are intentionally exempt. Semantic scopes carrying
    the ``read`` term fail closed unless every referenced operation exists and is
    explicitly classified non-mutating by the active Gateway operation registry.
    Semantic ``write`` scopes may contain either read or write operations.
    """
    if not scope.semantic_terms or "read" not in scope.semantic_terms:
        return ScopeValidation(scope.name, True)

    mutating = []
    unknown = []
    for operation in sorted(scope.operations):
        callable_ = gateway.ops.resolve(operation)
        if callable_ is None:
            unknown.append(operation)
            continue
        declared = getattr(callable_, "__gway_mutates__", None)
        if declared is None:
            declared = getattr(callable_, "mutates", None)
        if declared is None:
            unknown.append(operation)
        elif bool(declared):
            mutating.append(operation)

    return ScopeValidation(
        scope.name,
        not mutating and not unknown,
        tuple(mutating),
        tuple(unknown),
    )


def require_valid_scope(gateway, scope):
    """Return a scope or raise a diagnostic error for unsafe semantic reads."""
    result = validate_scope(gateway, scope)
    if result.valid:
        return scope

    details = []
    if result.mutating:
        details.append("mutating: " + ", ".join(result.mutating))
    if result.unknown:
        details.append("unclassified or unavailable: " + ", ".join(result.unknown))
    raise ValueError(
        f"Semantic read scope {scope.name} is unsafe (" + "; ".join(details) + ")"
    )


def validate_definitions(gateway, definitions):
    """Validate explicit semantic scope definitions before publication."""
    from .scopes import Scope

    results = []
    for name, definition in dict(definitions).items():
        definition = dict(definition)
        scope = Scope(
            str(name),
            frozenset(definition.get("operations", ())),
            frozenset(definition.get("environment", ())),
            None,
            frozenset(
                str(term).strip().lower()
                for term in definition.get("semantic_terms", ())
                if str(term).strip()
            ),
        )
        results.append(require_valid_scope(gateway, scope))
    return tuple(results)
