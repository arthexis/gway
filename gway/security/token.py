"""Gateway-bound opaque security token commands."""

from .tokens import TokenRegistry


class Controller:
    """Manage opaque bearer tokens in the active Gateway security registry."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        """Return the token registry bound to the active Gateway security path."""
        return TokenRegistry(self.gateway.security_path)

    def create(self, name, *scopes, expires=None):
        """Issue a token and return its bearer secret exactly once.

        Args:
            name: Stable token subject/name.
            scopes: Named scopes to bind.
            expires: Optional timezone-aware ISO-8601 expiry timestamp.
        """
        return self.registry.create(
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

    def disable(self, name):
        """Disable one token without removing its scope bindings."""
        return self.registry.disable(name)

    def enable(self, name):
        """Re-enable one disabled token."""
        return self.registry.enable(name)

    def set(self, name, *scopes):
        """Replace the complete named-scope binding set for one token."""
        return self.registry.replace_scopes(name, scopes)

    def bind(self, name, scope):
        """Bind one additional scope to a token."""
        return self.registry.bind(name, scope)

    def unbind(self, name, scope):
        """Remove one scope binding from a token."""
        return self.registry.unbind(name, scope)
