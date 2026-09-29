"""Gateway-bound OAuth token inspection commands."""

from .oauth import OAuthRegistry


class Controller:
    """Inspect and revoke issued OAuth access and refresh tokens."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        return OAuthRegistry(self.gateway.security_path)

    def show(self, public_id, *, mutate=True):
        """Return safe metadata for one issued OAuth token by public id."""
        return self.registry.credential(public_id, readonly=not mutate)

    def list(self, *, mutate=True):
        """Return safe metadata for issued OAuth access and refresh tokens."""
        return self.registry.credentials(readonly=not mutate)

    def clear(self):
        """Revoke every issued OAuth access and refresh token."""
        return self.registry.revoke_all_credentials()
