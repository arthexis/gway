"""Gateway-bound OAuth grant inspection commands."""

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

    def show(self, grant_id: int, *, mutate=True):
        grant = self.registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        return grant

    def list(self, *, mutate=True):
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
        return self.registry.revoke_grant(grant_id)
