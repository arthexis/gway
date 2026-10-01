"""Validation and mutation summaries for curated security scopes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeValidation:
    """Validation and live-binding classification for one curated scope."""

    name: str
    valid: bool
    mutating: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    registered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def mutation_capable(self):
        return bool(self.mutating or self.unknown)


def validate_scope(gateway, scope):
    """Classify live bindings and mutation behavior from exact members.

    Scope names carry no security semantics. A scope is provably non-mutating
    only when every member operation exists and explicitly declares itself
    non-mutating. Missing or unclassified operations are conservatively treated
    as mutation-capable, but they do not make the curated scope definition
    invalid. Missing bindings are reported separately so operators can audit
    stale exact grants without conflating them with registered-but-unclassified
    operations.
    """
    mutating = []
    unknown = []
    registered = []
    missing = []
    for operation in sorted(scope.operations):
        if operation == "__all__":
            unknown.append(operation)
            continue
        callable_ = gateway.ops.resolve(operation)
        if callable_ is None:
            missing.append(operation)
            unknown.append(operation)
            continue
        registered.append(operation)
        declared = getattr(callable_, "__gway_mutates__", None)
        if declared is None:
            declared = getattr(callable_, "mutates", None)
        if declared is None:
            unknown.append(operation)
        elif bool(declared):
            mutating.append(operation)

    return ScopeValidation(
        scope.name,
        True,
        tuple(mutating),
        tuple(unknown),
        tuple(registered),
        tuple(missing),
    )


def require_valid_scope(gateway, scope):
    """Return a curated scope after computing its mutation classification."""
    validate_scope(gateway, scope)
    return scope


def validate_definitions(gateway, definitions):
    """Validate explicit scope definitions and return their summaries."""
    from .scopes import Scope, ScopeRegistry

    results = []
    for name, definition in dict(definitions).items():
        definition = dict(definition)
        unknown = set(definition) - {"operations", "environment"}
        if unknown:
            raise ValueError(
                f"Unknown scope fields for {name}: {', '.join(sorted(unknown))}"
            )
        scope = Scope(
            ScopeRegistry._name(name),
            ScopeRegistry._grants(
                definition.get("operations", ()), label="operation"
            ),
            ScopeRegistry._grants(
                definition.get("environment", ()), label="environment"
            ),
        )
        results.append(validate_scope(gateway, scope))
    return tuple(results)
