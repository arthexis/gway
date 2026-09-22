"""OAuth discovery metadata for G-Way remote-access resources."""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


def _public_url(value, *, label, allow_insecure_loopback=False):
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty URL")
    parsed = urlsplit(text)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not contain user information")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not contain query or fragment components")
    if not parsed.hostname:
        raise ValueError(f"{label} must contain a host")
    secure = parsed.scheme == "https"
    loopback = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }
    if not secure and not (allow_insecure_loopback and loopback):
        raise ValueError(f"{label} must use HTTPS")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


@dataclass(frozen=True)
class RemoteOAuthMetadata:
    """Canonical public OAuth metadata for one remote protected resource."""

    issuer: str
    resource: str

    @classmethod
    def from_origin(
        cls,
        origin,
        *,
        resource_path="/mcp",
        allow_insecure_loopback=False,
    ):
        origin = _public_url(
            origin,
            label="OAuth issuer origin",
            allow_insecure_loopback=allow_insecure_loopback,
        )
        parsed = urlsplit(origin)
        if parsed.path:
            raise ValueError("OAuth issuer origin must not contain a path")
        resource_path = "/" + str(resource_path).strip().strip("/")
        if resource_path == "/":
            raise ValueError("OAuth protected resource path must be non-empty")
        resource = urlunsplit(
            (parsed.scheme, parsed.netloc, resource_path, "", "")
        )
        return cls(origin, resource)

    @property
    def authorization_endpoint(self):
        return f"{self.issuer}/oauth/authorize"

    @property
    def token_endpoint(self):
        return f"{self.issuer}/oauth/token"

    @property
    def revocation_endpoint(self):
        return f"{self.issuer}/oauth/revoke"

    @property
    def protected_resource_metadata_path(self):
        path = urlsplit(self.resource).path
        return f"/.well-known/oauth-protected-resource{path}"

    @property
    def authorization_server_metadata_path(self):
        return "/.well-known/oauth-authorization-server"

    def protected_resource_document(self):
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "bearer_methods_supported": ["header"],
        }

    def authorization_server_document(self):
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "revocation_endpoint": self.revocation_endpoint,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "authorization_response_iss_parameter_supported": True,
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "client_id_metadata_document_supported": True,
            "protected_resources": [self.resource],
        }
