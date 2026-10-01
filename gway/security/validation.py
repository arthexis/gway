"""Validation and mutation summaries for curated security scopes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeValidation:
    """Validation and mutation classification for one curated scope."""

    name: str
    valid: bool
    mutating: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()

    @property
    def mutation_capable(self):
        return bool(self.mutating or self.unknown)


def validate_scope(gateway, scope):
    """Classify mutation behavior from exact member-operation metadata.

    Scope names carry no security semantics. A scope is provably non-mutating
    only when every member operation exists and explicitly declares itself
    non-mutating. Missing or unclassified operations are conservatively treated
    as mutation-capable, but they do not make the curated scope definition
    invalid.
    """
    mutating = []
    unknown = []
    for operation in sorted(scope.operations):
        if operation == "__all__":
            unknown.append(operation)
            continue
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
        True,
        tuple(mutating),
        tuple(unknown),
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
