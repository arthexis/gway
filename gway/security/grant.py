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
        """Return one persisted OAuth grant."""
        grant = self.registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        return grant

    def inspect(self, grant_id: int, *, mutate=True):
        """Show stored and currently effective OAuth scope authority."""
        registry = self.registry
        grant = registry.get_grant(grant_id, readonly=not mutate)
        if grant is None:
            raise LookupError(f"Unknown OAuth grant: {grant_id}")
        link = registry.get_link(grant.link_name, readonly=not mutate)
        if link is None:
            raise LookupError(f"Unknown OAuth link: {grant.link_name}")
        token = registry.tokens.require(link.token_name, readonly=not mutate)
        effective_names = grant.scopes & token.scopes
        effective = registry.scopes.resolve(effective_names, readonly=not mutate)
        return {
            "grant_id": grant.id,
            "link": grant.link_name,
            "client_id": grant.client_id,
            "resource": grant.resource,
            "revoked": grant.revoked_at is not None,
            "scopes": sorted(grant.scopes),
            "effective_scopes": sorted(effective_names),
            "effective_operations": sorted(effective.operations),
            "effective_environment": sorted(effective.environment),
        }

    def list(self, *, mutate=True):
        """Return persisted OAuth grants."""
        return self.registry.grants(readonly=not mutate)

    def set(self, grant_id: int, *scopes):
        """Replace the curated scope bindings for one OAuth grant."""
        return self.registry.replace_grant_scopes(grant_id, scopes)

    def bind(self, grant_id: int, scope):
        """Bind one curated scope to an OAuth grant."""
        return self.registry.bind_grant_scope(grant_id, scope)

    def unbind(self, grant_id: int, scope):
        """Remove one curated scope from an OAuth grant."""
        return self.registry.unbind_grant_scope(grant_id, scope)

    def revoke(self, grant_id: int):
        """Revoke one OAuth grant."""
        return self.registry.revoke_grant(grant_id)
