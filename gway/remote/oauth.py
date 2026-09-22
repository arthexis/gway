"""OAuth authorization-code protocol for the shared remote service."""

from dataclasses import dataclass
import ipaddress
import json
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..security.oauth import OAuthAuthenticationError


class OAuthProtocolError(ValueError):
    """Standards-shaped OAuth protocol error."""

    def __init__(self, error, description=None, *, status=400):
        super().__init__(description or error)
        self.error = str(error)
        self.description = None if description is None else str(description)
        self.status = int(status)

    def payload(self):
        result = {"error": self.error}
        if self.description:
            result["error_description"] = self.description
        return result


@dataclass(frozen=True)
class ResolvedOAuthClient:
    client_id: str
    redirect_uris: frozenset[str]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OAuthClientResolver:
    """Resolve registered clients or HTTPS Client ID Metadata Documents."""

    def __init__(self, registry, *, fetcher=None):
        self.registry = registry
        self.fetcher = self._fetch_cimd if fetcher is None else fetcher

    @staticmethod
    def _client_url(client_id):
        parsed = urlsplit(str(client_id))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path in {"", "/"}
        ):
            raise OAuthProtocolError("invalid_client", "CIMD client_id must be an HTTPS document URL")
        return parsed

    @staticmethod
    def _require_public_host(hostname, port):
        try:
            addresses = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise OAuthProtocolError("invalid_client", "CIMD host cannot be resolved") from error
        if not addresses:
            raise OAuthProtocolError("invalid_client", "CIMD host cannot be resolved")
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if not address.is_global:
                raise OAuthProtocolError("invalid_client", "CIMD host must resolve only to public addresses")

    @classmethod
    def _fetch_cimd(cls, client_id):
        parsed = cls._client_url(client_id)
        cls._require_public_host(parsed.hostname, parsed.port)
        opener = build_opener(_NoRedirect)
        request = Request(
            client_id,
            headers={"Accept": "application/json", "User-Agent": "gway-oauth-cimd/1"},
        )
        try:
            with opener.open(request, timeout=5) as response:
                payload = response.read(65537)
        except Exception as error:
            raise OAuthProtocolError("invalid_client", "CIMD document could not be fetched") from error
        if len(payload) > 65536:
            raise OAuthProtocolError("invalid_client", "CIMD document is too large")
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OAuthProtocolError("invalid_client", "CIMD document is not valid JSON") from error
        if not isinstance(document, dict):
            raise OAuthProtocolError("invalid_client", "CIMD document must be a JSON object")
        return document

    def resolve(self, client_id):
        client_id = str(client_id or "").strip()
        if not client_id:
            raise OAuthProtocolError("invalid_client", "client_id is required")

        registered = self.registry.get_client(client_id)
        if registered is not None:
            if registered.disabled:
                raise OAuthProtocolError("invalid_client", "OAuth client is disabled")
            return ResolvedOAuthClient(client_id, registered.redirect_uris)

        self._client_url(client_id)
        document = self.fetcher(client_id)
        if not isinstance(document, dict) or document.get("client_id") != client_id:
            raise OAuthProtocolError("invalid_client", "CIMD client_id does not match its document URL")
        redirects = document.get("redirect_uris")
        if not isinstance(redirects, list) or not redirects:
            raise OAuthProtocolError("invalid_client", "CIMD redirect_uris are required")
        redirects = frozenset(str(uri) for uri in redirects if str(uri).strip())
        if not redirects:
            raise OAuthProtocolError("invalid_client", "CIMD redirect_uris are required")

        methods = document.get("token_endpoint_auth_methods")
        if methods is None:
            method = document.get("token_endpoint_auth_method")
            methods = ["none"] if method is None else [method]
        if not isinstance(methods, list) or "none" not in methods:
            raise OAuthProtocolError("invalid_client", "CIMD client must support public-client token exchange")
        return ResolvedOAuthClient(client_id, redirects)


class RemoteOAuthProtocol:
    """Authorization-code + PKCE behavior over the O0/O2 domain model."""

    access_lifetime_seconds = 900
    refresh_lifetime_seconds = 2592000

    def __init__(self, metadata, account, *, client_resolver=None):
        self.metadata = metadata
        self.account = account
        self.oauth = account.oauth
        self.clients = (
            OAuthClientResolver(self.oauth)
            if client_resolver is None
            else client_resolver
        )

    @staticmethod
    def _required(params, name):
        value = str(params.get(name) or "").strip()
        if not value:
            raise OAuthProtocolError("invalid_request", f"{name} is required")
        return value

    @staticmethod
    def _redirect_with(uri, values):
        parsed = urlsplit(uri)
        query = list(parse_qsl(parsed.query, keep_blank_values=True))
        query.extend((key, value) for key, value in values.items() if value is not None)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
        )

    def stage_authorization(self, session, params):
        if self._required(params, "response_type") != "code":
            raise OAuthProtocolError("unsupported_response_type")

        client_id = self._required(params, "client_id")
        client = self.clients.resolve(client_id)
        redirect_uri = self._required(params, "redirect_uri")
        if redirect_uri not in client.redirect_uris:
            raise OAuthProtocolError("invalid_request", "redirect_uri is not registered for this client")

        resource = self._required(params, "resource")
        if resource != self.metadata.resource:
            raise OAuthProtocolError("invalid_target", "resource does not match this protected resource")

        challenge = self._required(params, "code_challenge")
        if self._required(params, "code_challenge_method") != "S256":
            raise OAuthProtocolError("invalid_request", "PKCE S256 is required")
        if len(challenge) < 43 or len(challenge) > 128:
            raise OAuthProtocolError("invalid_request", "PKCE code_challenge has invalid length")

        scope = self._required(params, "scope")
        self.account.stage_consent(
            session,
            client_id,
            scope,
            resource=resource,
        )
        session.pending_redirect_uri = redirect_uri
        session.pending_state = None if params.get("state") is None else str(params["state"])
        session.pending_code_challenge = challenge
        return session

    def _clear_pending_authorization(self, session):
        session.pending_redirect_uri = None
        session.pending_state = None
        session.pending_code_challenge = None

    def finish_authorization(self, session, grant):
        redirect_uri = session.pending_redirect_uri
        state = session.pending_state
        challenge = session.pending_code_challenge
        if not redirect_uri or not challenge:
            raise OAuthProtocolError("invalid_request", "No OAuth authorization request is pending")

        try:
            if grant is None:
                values = {
                    "error": "access_denied",
                    "state": state,
                    "iss": self.metadata.issuer,
                }
            else:
                if grant.resource != self.metadata.resource:
                    raise OAuthProtocolError("invalid_target")
                issued = self.oauth.issue_authorization_code(
                    grant.id,
                    redirect_uri=redirect_uri,
                    code_challenge=challenge,
                )
                values = {
                    "code": issued.code,
                    "state": state,
                    "iss": self.metadata.issuer,
                }
            return self._redirect_with(redirect_uri, values)
        finally:
            self._clear_pending_authorization(session)

    def token(self, params):
        grant_type = self._required(params, "grant_type")
        client_id = self._required(params, "client_id")
        resource = self._required(params, "resource")
        if resource != self.metadata.resource:
            raise OAuthProtocolError("invalid_target")

        try:
            if grant_type == "authorization_code":
                grant = self.oauth.consume_authorization_code(
                    self._required(params, "code"),
                    redirect_uri=self._required(params, "redirect_uri"),
                    code_verifier=self._required(params, "code_verifier"),
                    client_id=client_id,
                    resource=resource,
                )
                issued = self.oauth.issue_tokens(
                    grant.id,
                    access_lifetime_seconds=self.access_lifetime_seconds,
                    refresh_lifetime_seconds=self.refresh_lifetime_seconds,
                )
            elif grant_type == "refresh_token":
                requested_scope = params.get("scope")
                issued = self.oauth.rotate_refresh(
                    self._required(params, "refresh_token"),
                    client_id=client_id,
                    resource=resource,
                    access_lifetime_seconds=self.access_lifetime_seconds,
                    refresh_lifetime_seconds=self.refresh_lifetime_seconds,
                )
                if requested_scope is not None:
                    requested = frozenset(str(requested_scope).split())
                    if requested != issued.grant.scopes:
                        self.oauth.revoke(issued.access_token)
                        self.oauth.revoke(issued.refresh_token)
                        raise OAuthProtocolError("invalid_scope", "Refresh cannot change the granted G-Way scopes")
            else:
                raise OAuthProtocolError("unsupported_grant_type")
        except OAuthAuthenticationError as error:
            raise OAuthProtocolError("invalid_grant") from error

        return {
            "access_token": issued.access_token,
            "token_type": "Bearer",
            "expires_in": self.access_lifetime_seconds,
            "refresh_token": issued.refresh_token,
            "scope": " ".join(sorted(issued.grant.scopes)),
            "resource": issued.grant.resource,
        }

    def revoke(self, params):
        token = self._required(params, "token")
        try:
            self.oauth.revoke(token)
        except OAuthAuthenticationError:
            pass
        return {}
