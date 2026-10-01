"""Gateway-bound named security scope commands."""

from pathlib import Path

try:
    import tomllib as _toml
except ModuleNotFoundError:
    import tomli as _toml

from . import semantics as scope_semantics
from .scopes import Scope, ScopeRegistry
from .validation import (
    require_valid_scope,
    validate_definitions,
    validate_published,
    validate_scope,
)


__all__ = ()


class Controller:
    """Manage named scopes in the active Gateway security registry."""

    def __init__(self, gateway):
        self.gateway = gateway

    def __main__(self, *, mutate=True):
        """Return all named security scopes."""
        return self.list(mutate=mutate)

    def _registry(self, *, converge=False):
        """Return the scope registry, converging published scopes when requested."""
        if converge:
            self.gateway.converge_security_scopes()
        return ScopeRegistry(self.gateway.security_path)

    @property
    def registry(self):
        """Return the scope registry bound to the active Gateway security path."""
        return self._registry()

    def create(self, name):
        """Create an empty named security scope."""
        return self.registry.create(name)

    def show(self, name, *, mutate=True):
        """Return one named security scope."""
        return self._registry(converge=mutate).require(name, readonly=not mutate)

    def list(self, *, mutate=True):
        """Return all named security scopes."""
        return self._registry(converge=mutate).all(readonly=not mutate)

    def current(self, *, mutate=False):
        """Return the caller's current effective authority."""
        del mutate
        authority = self.gateway.authorization
        if authority is None:
            return {
                "constrained": False,
                "operations": None,
                "environment": None,
            }
        return {
            "constrained": True,
            "operations": sorted(authority.operations),
            "environment": (
                []
                if authority.environment is None
                else sorted(authority.environment)
            ),
        }

    def converge(self, *, retire_missing=True):
        """Validate and atomically converge all currently published scopes."""
        from .defaults import converge_scope_registry

        validate_published(self.gateway)
        return converge_scope_registry(
            self.registry,
            getattr(self.gateway, "_published_scopes", {}),
            retire_missing=retire_missing,
            report=True,
        )

    def rename(self, name, new_name):
        """Rename one scope while preserving grants and bearer bindings."""
        return self.registry.rename(name, new_name)

    def delete(self, name):
        """Delete one named security scope."""
        return self.registry.remove(name)

    @staticmethod
    def _environment_values(environment):
        if environment is None:
            return ()
        if isinstance(environment, str):
            return tuple(item.strip() for item in environment.split(",") if item.strip())
        return tuple(environment)

    @staticmethod
    def _semantic_values(semantic=None, semantic_terms=None):
        values = semantic_terms if semantic_terms is not None else semantic
        if values is None:
            return ()
        if isinstance(values, str):
            return tuple(item.strip() for item in values.split(",") if item.strip())
        return tuple(values)

    def set(self, name, *operations, environment=None, semantic=None, semantic_terms=None):
        """Replace one scope using operation grants and optional metadata."""
        environment_values = self._environment_values(environment)
        semantic_values = self._semantic_values(semantic, semantic_terms)
        candidate = Scope(
            str(name),
            frozenset(operations),
            frozenset(environment_values),
            None,
            frozenset(str(value).strip().lower() for value in semantic_values),
        )
        require_valid_scope(self.gateway, candidate)
        return self.registry.replace(
            name,
            operations=operations,
            environment=environment_values,
            semantic_terms=semantic_values,
        )

    def add(self, name, *operations, environment=None):
        """Add operation and environment grants to an existing scope."""
        existing = self.registry.require(name)
        candidate = Scope(
            existing.name,
            existing.operations | frozenset(operations),
            existing.environment | frozenset(self._environment_values(environment)),
            existing.owner,
            existing.semantic_terms,
        )
        require_valid_scope(self.gateway, candidate)
        return self.registry.update_grants(
            name,
            add_operations=operations,
            add_environment=self._environment_values(environment),
        )

    def remove(self, name, *operations, environment=None):
        """Remove operation and environment grants from an existing scope."""
        return self.registry.update_grants(
            name,
            remove_operations=operations,
            remove_environment=self._environment_values(environment),
        )

    def contains(self, name, *terms, mutate=True):
        """Return whether a semantic scope contains all requested terms."""
        registry = self._registry(converge=mutate)
        scope = registry.require(name, readonly=not mutate)
        return scope_semantics.contains(scope, terms)

    def match(self, *terms, mutate=True):
        """Return semantic leaf scopes matching all requested terms."""
        registry = self._registry(converge=mutate)
        return scope_semantics.match(
            registry.all(readonly=not mutate),
            terms,
        )

    def union(self, *names, mutate=True):
        """Return the least broad semantic authority containing named scopes."""
        registry = self._registry(converge=mutate)
        scopes = tuple(
            registry.require(name, readonly=not mutate)
            for name in names
        )
        return scope_semantics.union(scopes)

    def resolve(self, *values, semantic=False, mutate=True):
        """Resolve exact named scopes, or semantic terms when explicitly requested."""
        registry = self._registry(converge=mutate)
        if semantic:
            return scope_semantics.resolve(
                registry.all(readonly=not mutate),
                values,
            )
        return registry.resolve(values, readonly=not mutate)

    def validate(self, name, *, mutate=True):
        """Validate semantic safety of one existing scope."""
        registry = self._registry(converge=mutate)
        scope = registry.require(name, readonly=not mutate)
        return validate_scope(self.gateway, scope)

    @staticmethod
    def _definitions(path):
        path = Path(path).expanduser()
        with path.open("rb") as stream:
            document = _toml.load(stream)
        scopes = document.get("scopes")
        if not isinstance(scopes, dict):
            raise ValueError("scope TOML requires a [scopes] table")
        return scopes

    def apply(self, path, *, absolute=False):
        """Apply scope definitions, adding grants unless absolute is requested."""
        scopes = self._definitions(path)
        validate_definitions(self.gateway, scopes)
        if absolute:
            return self.registry.replace_many(scopes)
        return self.registry.add_many(scopes)

    def replace_from(self, path):
        """Replace complete definitions for scopes declared in a TOML file."""
        definitions = self._definitions(path)
        validate_definitions(self.gateway, definitions)
        return self.registry.replace_many(definitions)

    @staticmethod
    def _toml_string(value):
        value = str(value)
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def export(self, to=None):
        """Export all scopes as stable TOML, optionally writing to a file."""
        lines = []
        for scope in self.registry.all():
            lines.append(f"[scopes.{self._toml_string(scope.name)}]")
            operations = ", ".join(
                self._toml_string(value) for value in sorted(scope.operations)
            )
            environment = ", ".join(
                self._toml_string(value) for value in sorted(scope.environment)
            )
            semantic_terms = ", ".join(
                self._toml_string(value) for value in sorted(scope.semantic_terms)
            )
            lines.append(f"operations = [{operations}]")
            lines.append(f"environment = [{environment}]")
            if scope.semantic_terms:
                lines.append(f"semantic_terms = [{semantic_terms}]")
            lines.append("")
        rendered = "\n".join(lines)
        if to is None:
            return rendered
        path = Path(to).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return str(path)
