"""Gateway-bound OAuth client registration commands."""

from .oauth import OAuthRegistry


class Controller:
    """Manage OAuth clients in the active Gateway security registry."""

    def __init__(self, gateway):
        self.gateway = gateway

    @property
    def registry(self):
        """Return the OAuth registry bound to the active Gateway security path."""
        return OAuthRegistry(self.gateway.security_path)

    def create(
        self,
        client_id,
        *redirect_uris,
        confidential=False,
        method=None,
        metadata_url=None,
    ):
        """Register one OAuth client and return its secret exactly once when confidential.

        Args:
            client_id: Stable OAuth client identifier.
            redirect_uris: Exact allowed redirect URIs.
            confidential: Generate a client secret for confidential authentication.
            method: Token endpoint auth method: none, client_secret_post, or client_secret_basic.
            metadata_url: Optional OAuth client metadata URL.
        """
        issued = self.registry.create_client(
            client_id,
            redirect_uris=redirect_uris,
            metadata_url=metadata_url,
            confidential=confidential,
            token_endpoint_auth_method=method,
        )
        secret = getattr(issued, "client_secret", None)
        return issued if secret is None else secret

    def show(self, client_id, *, mutate=True):
        """Return safe metadata for one OAuth client."""
        return self.registry.require_client(client_id, readonly=not mutate)

    def list(self, *, mutate=True):
        """Return safe metadata for all registered OAuth clients."""
        return self.registry.clients(readonly=not mutate)

    def delete(self, client_id):
        """Delete one OAuth client registration."""
        return self.registry.remove_client(client_id)

    def disable(self, client_id):
        """Disable one OAuth client without deleting it."""
        return self.registry.disable_client(client_id)

    def enable(self, client_id):
        """Re-enable one disabled OAuth client."""
        return self.registry.enable_client(client_id)
