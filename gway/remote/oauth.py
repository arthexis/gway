"""OAuth authorization-code protocol for the shared remote service."""

from dataclasses import dataclass
import base64
import binascii
import ipaddress
import json
import socket
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit
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
    token_endpoint_auth_method: str = "none"


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
            return ResolvedOAuthClient(
                client_id,
                registered.redirect_uris,
                registered.token_endpoint_auth_method,
            )

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
        return ResolvedOAuthClient(client_id, redirects, "none")


class RemoteOAuthProtocol:
    """Authorization-code behavior with PKCE policy over the O0/O2 domain model."""

    access_lifetime_seconds = 900
    refresh_lifetime_seconds = 2592000

    def __init__(
        self,
        metadata,
        account,
        *,
        client_resolver=None,
        allow_confidential_without_pkce=False,
    ):
        self.metadata = metadata
        self.account = account
        self.oauth = account.oauth
        self.allow_confidential_without_pkce = bool(
            allow_confidential_without_pkce
        )
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

        challenge = str(params.get("code_challenge") or "").strip()
        method = str(params.get("code_challenge_method") or "").strip()
        pkce_required = not (
            self.allow_confidential_without_pkce
            and client.token_endpoint_auth_method
            in {"client_secret_post", "client_secret_basic"}
        )
        if pkce_required and not challenge:
            raise OAuthProtocolError(
                "invalid_request",
                "code_challenge is required",
            )
        if challenge:
            if method != "S256":
                raise OAuthProtocolError(
                    "invalid_request",
                    "PKCE S256 is required",
                )
            if len(challenge) != 43 or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in challenge
            ):
                raise OAuthProtocolError(
                    "invalid_request",
                    "PKCE S256 code_challenge is malformed",
                )
        elif method:
            raise OAuthProtocolError(
                "invalid_request",
                "code_challenge is required when code_challenge_method is supplied",
            )

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
        if not redirect_uri:
            raise OAuthProtocolError(
                "invalid_request",
                "No OAuth authorization request is pending",
            )

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

    @staticmethod
    def _basic_client(headers):
        authorization = str((headers or {}).get("authorization") or "")
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.casefold() != "basic":
            return None
        try:
            decoded = base64.b64decode(
                credential.strip(),
                validate=True,
            ).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise OAuthProtocolError(
                "invalid_client",
                "Malformed HTTP Basic client credentials",
                status=401,
            ) from None
        client_id, separator, client_secret = decoded.partition(":")
        if not separator:
            raise OAuthProtocolError(
                "invalid_client",
                "Malformed HTTP Basic client credentials",
                status=401,
            )
        return unquote_plus(client_id), unquote_plus(client_secret)

    def _authenticate_token_client(self, params, headers=None):
        basic = self._basic_client(headers)
        form_secret = params.get("client_secret")

        if basic is not None:
            if form_secret not in (None, ""):
                raise OAuthProtocolError(
                    "invalid_request",
                    "Use only one OAuth client authentication method",
                )
            client_id, client_secret = basic
            method = "client_secret_basic"
        else:
            client_id = self._required(params, "client_id")
            if form_secret not in (None, ""):
                client_secret = str(form_secret)
                method = "client_secret_post"
            else:
                client_secret = None
                method = "none"

        client = self.clients.resolve(client_id)
        if method != client.token_endpoint_auth_method:
            raise OAuthProtocolError(
                "invalid_client",
                "OAuth client authentication method does not match registration",
                status=401,
            )

        registered = self.oauth.get_client(client_id)
        if registered is not None:
            try:
                self.oauth.authenticate_client(
                    client_id,
                    client_secret=client_secret,
                    token_endpoint_auth_method=method,
                )
            except OAuthAuthenticationError as error:
                raise OAuthProtocolError(
                    "invalid_client",
                    "OAuth client authentication failed",
                    status=401,
                ) from error
        elif method != "none":
            raise OAuthProtocolError(
                "invalid_client",
                "Dynamic OAuth clients must use public-client authentication",
                status=401,
            )
        return client

    def token(self, params, *, headers=None):
        grant_type = self._required(params, "grant_type")
        client = self._authenticate_token_client(params, headers)
        client_id = client.client_id
        resource = self._required(params, "resource")
        if resource != self.metadata.resource:
            raise OAuthProtocolError("invalid_target")

        try:
            if grant_type == "authorization_code":
                grant = self.oauth.consume_authorization_code(
                    self._required(params, "code"),
                    redirect_uri=self._required(params, "redirect_uri"),
                    code_verifier=(
                        str(params.get("code_verifier") or "").strip() or None
                    ),
                    client_id=client_id,
                    resource=resource,
                )
                issued = self.oauth.issue_tokens(
                    grant.id,
                    access_lifetime_seconds=self.access_lifetime_seconds,
                    refresh_lifetime_seconds=self.refresh_lifetime_seconds,
                )
            elif grant_type == "refresh_token":
                if params.get("scope") is not None:
                    raise OAuthProtocolError(
                        "invalid_scope",
                        "Refresh cannot change the granted G-Way scopes",
                    )
                issued = self.oauth.rotate_refresh(
                    self._required(params, "refresh_token"),
                    client_id=client_id,
                    resource=resource,
                    access_lifetime_seconds=self.access_lifetime_seconds,
                    refresh_lifetime_seconds=self.refresh_lifetime_seconds,
                )
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
