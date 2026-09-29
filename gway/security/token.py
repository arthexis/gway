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
        """Return the token registry bound to the active Gateway security path."""
        return self._registry()

    def scopes(self, *, mutate=True):
        """Return named security scopes available for token binding."""
        return self._registry(converge=mutate).scopes.all(readonly=not mutate)

    def create(self, name, *scopes, expires=None):
        """Issue a token and return its bearer secret exactly once.

        Args:
            name: Stable token subject/name.
            scopes: Named scopes to bind.
            expires: Optional timezone-aware ISO-8601 expiry timestamp.
        """
        return self._registry(converge=True).create(
            name,
            scopes=scopes,
            expires_at=expires,
        ).bearer

    def show(self, name, *, mutate=True):
        """Return safe metadata for one named token."""
        return self.registry.require(name, readonly=not mutate)

    def list(self, *, mutate=True):
        """Return safe metadata for all named tokens."""
        return self.registry.all(readonly=not mutate)

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
        """Replace the complete named-scope binding set for one token."""
        return self._registry(converge=True).replace_scopes(name, scopes)

    def bind(self, name, scope):
        """Bind one additional scope to a token."""
        return self._registry(converge=True).bind(name, scope)

    def unbind(self, name, scope):
        """Remove one scope binding from a token."""
        return self.registry.unbind(name, scope)
