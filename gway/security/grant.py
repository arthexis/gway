"""Gateway-bound OAuth grant inspection commands."""

from . import semantics as scope_semantics
from .oauth import OAuthRegistry


class Controller:
    """Inspect and revoke OAuth grants."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        return OAuthRegistry(self.gateway.security_path)

    @staticmethod
    def _union_values(value):
        if value is None:
            return ()
        if isinstance(value, str):
            return (tuple(value.replace(",", " ").split()),)
        values = tuple(value)
        if values and all(isinstance(item, str) for item in values):
            return (values,)
        return values

    @staticmethod
    def _resolution_payload(resolution):
        return {
            "terms": sorted(resolution.terms),
            "exact_scopes": list(resolution.exact_scopes),
            "conjunction": list(resolution.conjunction),
            "matched_scopes": list(resolution.scopes),
            "operations": sorted(resolution.operations),
        }

    def show(self, grant_id: int, *, mutate=True):
        """Return one persisted OAuth grant."""
        grant = self.registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        return grant

    def inspect(self, grant_id: int, *, mutate=True):
        """Show stored and currently effective OAuth scope authority."""
        registry = self.registry
        grant = registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        link = registry.get_link(grant.link_name, readonly=not mutate)
        if link is None:
            raise LookupError(f"Unknown OAuth link: {grant.link_name}")
        token = registry.tokens.require(link.token_name, readonly=not mutate)
        effective_exact_names = grant.scopes & token.scopes
        effective_union_terms = tuple(
            sorted(
                terms
                for terms in grant.union_scopes
                if registry._union_is_within(terms, token.union_scopes)
            )
        )
        leaves = registry.scopes.all(readonly=not mutate)
        exact = registry.scopes.resolve(effective_exact_names, readonly=not mutate)
        union_resolutions = tuple(
            scope_semantics.resolve(leaves, union_terms)
            for union_terms in effective_union_terms
        )
        operations = set(exact.operations)
        for resolution in union_resolutions:
            operations.update(resolution.operations)
        return {
            "grant_id": grant.id,
            "link": grant.link_name,
            "client_id": grant.client_id,
            "resource": grant.resource,
            "revoked": grant.revoked_at is not None,
            "exact_scopes": sorted(grant.scopes),
            "effective_exact_scopes": sorted(effective_exact_names),
            "union_scopes": [
                {
                    "terms": list(terms),
                    "effective": terms in effective_union_terms,
                }
                for terms in sorted(grant.union_scopes)
            ],
            "effective_union_scopes": [
                self._resolution_payload(resolution)
                for resolution in union_resolutions
            ],
            "matched_scopes": sorted(
                {
                    scope
                    for resolution in union_resolutions
                    for scope in resolution.scopes
                }
            ),
            "effective_operations": sorted(operations),
            "effective_environment": sorted(exact.environment),
        }

    def list(self, *, mutate=True):
        """Return persisted OAuth grants."""
        return self.registry.grants(readonly=not mutate)

    def set(self, grant_id: int, *scopes, union=None):
        """Replace exact bindings and optionally replace union bindings."""
        grant = self.registry.replace_grant_scopes(grant_id, scopes)
        if union is not None:
            grant = self.registry.replace_grant_union_scopes(
                grant_id, self._union_values(union)
            )
        return grant

    def bind(self, grant_id: int, scope=None, *, union=None):
        """Bind one exact scope or one union scope to an OAuth grant."""
        if union is not None:
            if scope is not None:
                raise ValueError("bind accepts either an exact scope or --union, not both")
            values = self._union_values(union)
            if len(values) != 1:
                raise ValueError("bind --union requires one union scope")
            return self.registry.bind_grant_union(grant_id, *values[0])
        if scope is None:
            raise ValueError("bind requires an exact scope or --union")
        return self.registry.bind_grant_scope(grant_id, scope)

    def unbind(self, grant_id: int, scope=None, *, union=None):
        """Remove one exact scope or one union scope from an OAuth grant."""
        if union is not None:
            if scope is not None:
                raise ValueError("unbind accepts either an exact scope or --union, not both")
            values = self._union_values(union)
            if len(values) != 1:
                raise ValueError("unbind --union requires one union scope")
            return self.registry.unbind_grant_union(grant_id, *values[0])
        if scope is None:
            raise ValueError("unbind requires an exact scope or --union")
        return self.registry.unbind_grant_scope(grant_id, scope)

    def revoke(self, grant_id: int):
        """Revoke one OAuth grant."""
        return self.registry.revoke_grant(grant_id)
