"""Normalize native G-Way and OAuth bearer credentials into one authority."""

from dataclasses import dataclass

from .oauth import OAuthAuthenticationError, OAuthRegistry
from .scopes import EffectiveScope
from .tokens import AuthenticationError, TokenRegistry


class BearerAuthenticationError(PermissionError):
    """Raised when a bearer cannot authenticate for the requested resource."""

    def __init__(self):
        super().__init__("Invalid bearer token")


@dataclass(frozen=True)
class AuthenticatedBearer:
    """Transport-neutral authenticated identity plus current G-Way authority."""

    kind: str
    principal: str
    client_id: str
    scopes: frozenset[str]
    authority: EffectiveScope


def authenticate_bearer(
    bearer,
    *,
    resource=None,
    path=None,
    tokens=None,
    oauth=None,
):
    """Authenticate one supported bearer against the shared security registry.

    Native G-Way tokens are accepted directly. OAuth access tokens additionally
    require an exact protected-resource match.
    """
    value = str(bearer or "").strip()
    if not value:
        raise BearerAuthenticationError()

    try:
        if value.startswith("gwt_"):
            if tokens is None:
                tokens = TokenRegistry() if path is None else TokenRegistry(path)
            identity = tokens.authenticate(value)
            return AuthenticatedBearer(
                kind="gway",
                principal=identity.token.name,
                client_id=f"gway:{identity.token.name}",
                scopes=identity.token.scopes,
                authority=identity.authority,
            )

        if value.startswith("gwa_"):
            if oauth is None:
                oauth = OAuthRegistry() if path is None else OAuthRegistry(path)
            identity = oauth.authenticate_access(value)
            if resource is None or identity.grant.resource != str(resource):
                raise BearerAuthenticationError()
            return AuthenticatedBearer(
                kind="oauth",
                principal=identity.grant.link_name,
                client_id=identity.grant.client_id,
                scopes=identity.grant.scopes,
                authority=identity.authority,
            )
    except (AuthenticationError, OAuthAuthenticationError):
        raise BearerAuthenticationError() from None

    raise BearerAuthenticationError()
