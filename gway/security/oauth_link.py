"""Gateway-bound OAuth link inspection commands."""

from .oauth import OAuthRegistry


class Controller:
    """Inspect and revoke OAuth account links."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        return OAuthRegistry(self.gateway.security_path)

    def show(self, name, *, mutate=True):
        """Return safe metadata for one OAuth link."""
        link = self.registry.get_link(name, readonly=not mutate)
        if link is None:
            raise LookupError(f"Unknown OAuth link: {name}")
        return link

    def list(self, *, mutate=True):
        """Return safe metadata for all OAuth links."""
        return self.registry.links(readonly=not mutate)

    def revoke(self, name):
        """Revoke one OAuth link and invalidate its grants."""
        return self.registry.revoke_link(name)
