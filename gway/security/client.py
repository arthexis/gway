"""GWAY command facade for OAuth client registrations."""

from .oauth import OAuthRegistry as _OAuthRegistry


_registry = None


def registry():
    """Return the process-local default OAuth registry."""
    global _registry
    if _registry is None:
        _registry = _OAuthRegistry()
    return _registry


def create(
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
    issued = registry().create_client(
        client_id,
        redirect_uris=redirect_uris,
        metadata_url=metadata_url,
        confidential=confidential,
        token_endpoint_auth_method=method,
    )
    secret = getattr(issued, "client_secret", None)
    return issued if secret is None else secret


def show(client_id, *, mutate=True):
    """Return safe metadata for one OAuth client."""
    return registry().require_client(client_id, readonly=not mutate)


def list(*, mutate=True):
    """Return safe metadata for all registered OAuth clients."""
    return registry().clients(readonly=not mutate)


def delete(client_id):
    """Delete one OAuth client registration."""
    return registry().remove_client(client_id)


def disable(client_id):
    """Disable one OAuth client without deleting it."""
    return registry().disable_client(client_id)


def enable(client_id):
    """Re-enable one disabled OAuth client."""
    return registry().enable_client(client_id)
