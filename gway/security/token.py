"""Gateway-bound opaque security token commands."""

from .tokens import TokenRegistry


__all__ = ()


class Controller:
    """Manage opaque bearer tokens in the active Gateway security registry."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _registry(self, *, converge=False):
        """Return the token registry, converging published scopes when requested."""
        if converge:
            self.gateway.converge_security_scopes()
        return TokenRegistry(self.gateway.security_path)

    @property
    def registry(self):
        return self._registry()

    def scopes(self, *, mutate=True):
        return self._registry(converge=mutate).scopes.all(readonly=not mutate)

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

    def create(self, name, *scopes, expires=None, union=None):
        """Issue a token with exact scopes and optional union-scope authority."""
        return self._registry(converge=True).create(
            name,
            scopes=scopes,
            union_scopes=self._union_values(union),
            expires_at=expires,
        ).bearer

    def show(self, name, *, mutate=True):
        return self.registry.require(name, readonly=not mutate)

    def list(self, *, mutate=True):
        return self.registry.all(readonly=not mutate)

    def delete(self, name):
        return self.registry.remove(name)

    def clear(self):
        return self.registry.clear()

    def disable(self, name):
        return self.registry.disable(name)

    def enable(self, name):
        return self.registry.enable(name)

    def set(self, name, *scopes, union=None):
        """Replace exact bindings and optionally replace union bindings."""
        registry = self._registry(converge=True)
        token = registry.replace_scopes(name, scopes)
        if union is not None:
            token = registry.replace_union_scopes(name, self._union_values(union))
        return token

    def bind(self, name, scope=None, *, union=None):
        """Bind one exact scope or one union scope to a token."""
        registry = self._registry(converge=True)
        if union is not None:
            if scope is not None:
                raise ValueError("bind accepts either an exact scope or --union, not both")
            values = self._union_values(union)
            if len(values) != 1:
                raise ValueError("bind --union requires one union scope")
            return registry.bind_union(name, *values[0])
        if scope is None:
            raise ValueError("bind requires an exact scope or --union")
        return registry.bind(name, scope)

    def unbind(self, name, scope=None, *, union=None):
        """Remove one exact scope or one union scope binding."""
        if union is not None:
            if scope is not None:
                raise ValueError("unbind accepts either an exact scope or --union, not both")
            values = self._union_values(union)
            if len(values) != 1:
                raise ValueError("unbind --union requires one union scope")
            return self.registry.unbind_union(name, *values[0])
        if scope is None:
            raise ValueError("unbind requires an exact scope or --union")
        return self.registry.unbind(name, scope)
