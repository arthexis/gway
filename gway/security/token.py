"""Gateway-bound opaque security token commands."""

from .tokens import TokenRegistry


__all__ = ()


class Controller:
    """Manage opaque bearer tokens in the active Gateway security registry."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _registry(self, *, converge=False):
        """Return the token registry, converging curated scopes when requested."""
        if converge:
            self.gateway.converge_security_scopes()
        return TokenRegistry(self.gateway.security_path)

    @property
    def registry(self):
        """Return the token registry bound to the active Gateway security path."""
        return self._registry()

    def scopes(self, *, mutate=True):
        """Return named security scopes available for token binding."""
        return self._registry(converge=mutate).scopes.all(readonly=not mutate)

    def create(self, name, *scopes, expires=None):
        """Issue a token bound to one or more curated named scopes."""
        return self._registry(converge=True).create(
            name,
            scopes=scopes,
            expires_at=expires,
        ).bearer

    def show(self, name, *, mutate=True):
        """Return safe metadata for one named token."""
        return self.registry.require(name, readonly=not mutate)

    def inspect(self, name, *, mutate=True):
        """Show curated scope bindings and effective authority for one token."""
        registry = self._registry(converge=mutate)
        token = registry.require(name, readonly=not mutate)
        exact = registry.scopes.resolve(token.scopes, readonly=not mutate)
        return {
            "name": token.name,
            "public_id": token.public_id,
            "disabled": token.disabled,
            "scopes": sorted(token.scopes),
            "effective_operations": sorted(exact.operations),
            "effective_environment": sorted(exact.environment),
        }

    def list(self, *, mutate=True):
        """Return safe metadata for all named tokens."""
        return self.registry.all(readonly=not mutate)

    def rename(self, name, new_name):
        """Rename one token without rotating its bearer or stable identity."""
        return self.registry.rename(name, new_name)

    def delete(self, name):
        """Permanently revoke and remove one named token."""
        return self.registry.remove(name)

    def clear(self):
        """Permanently revoke and remove every named token."""
        return self.registry.clear()

    def disable(self, name):
        """Disable one token without removing its scope bindings."""
        return self.registry.disable(name)

    def enable(self, name):
        """Re-enable one disabled token."""
        return self.registry.enable(name)

    def set(self, name, *scopes):
        """Replace the curated scope bindings for one token."""
        return self._registry(converge=True).replace_scopes(name, scopes)

    def bind(self, name, scope):
        """Bind one curated scope to a token."""
        return self._registry(converge=True).bind(name, scope)

    def unbind(self, name, scope):
        """Remove one curated scope binding from a token."""
        return self.registry.unbind(name, scope)
