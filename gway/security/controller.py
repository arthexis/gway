"""Gateway-bound security self-introspection."""


__all__ = ()


class Controller:
    """Expose the current caller identity and effective curated authority."""

    def __init__(self, gateway):
        self.gateway = gateway

    def whoami(self, *, mutate=False):
        """Return the current caller identity and effective authority."""
        del mutate
        authority = self.gateway.authorization
        if authority is None:
            return {
                "kind": "local",
                "principal": None,
                "client_id": None,
                "scopes": [],
                "constrained": False,
                "operations": None,
                "environment": None,
            }
        return {
            "kind": authority.kind or "external",
            "principal": authority.principal,
            "client_id": authority.client_id,
            "scopes": sorted(authority.scopes),
            "constrained": True,
            "operations": sorted(authority.operations),
            "environment": (
                []
                if authority.environment is None
                else sorted(authority.environment)
            ),
        }
