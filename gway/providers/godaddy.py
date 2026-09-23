"""GoDaddy provider binding registration."""

from ..bindings import env, secret


def register(gateway):
    """Register GoDaddy semantic credential bindings."""
    declarations = {
        "dns.godaddy.pat": (
            env("GODADDY_PAT", sensitive=True),
            secret("dns/godaddy/pat"),
        ),
        "dns.godaddy.api_key": (
            env("GODADDY_API_KEY", sensitive=True),
            env("GODADDY_KEY", sensitive=True),
            secret("dns/godaddy/key"),
        ),
        "dns.godaddy.api_secret": (
            env("GODADDY_API_SECRET", sensitive=True),
            env("GODADDY_SECRET", sensitive=True),
            secret("dns/godaddy/secret"),
        ),
    }
    for semantic_key, bindings in declarations.items():
        gateway.bind(semantic_key, *bindings, replace=False)
    return tuple(declarations)
