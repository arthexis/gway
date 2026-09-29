"""Gateway-bound OAuth grant inspection commands."""

from .oauth import OAuthRegistry


class Controller:
    """Inspect and revoke OAuth grants."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        return OAuthRegistry(self.gateway.security_path)

    def show(self, grant_id: int, *, mutate=True):
        """Return safe metadata for one OAuth grant."""
        grant = self.registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        return grant

    def list(self, *, mutate=True):
        """Return safe metadata for all OAuth grants."""
        return self.registry.grants(readonly=not mutate)

    def set(self, grant_id: int, *scopes):
        """Replace the complete scope binding set for one OAuth grant."""
        return self.registry.replace_grant_scopes(grant_id, scopes)

    def bind(self, grant_id: int, scope):
        """Bind one additional scope to an OAuth grant."""
        return self.registry.bind_grant_scope(grant_id, scope)

    def unbind(self, grant_id: int, scope):
        """Remove one scope binding from an OAuth grant."""
        return self.registry.unbind_grant_scope(grant_id, scope)

    def revoke(self, grant_id: int):
        """Revoke one OAuth grant and invalidate its credentials."""
        return self.registry.revoke_grant(grant_id)
