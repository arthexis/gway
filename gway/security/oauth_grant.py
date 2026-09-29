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

    def revoke(self, grant_id: int):
        """Revoke one OAuth grant and invalidate its credentials."""
        return self.registry.revoke_grant(grant_id)
