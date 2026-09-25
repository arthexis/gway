"""HTTP surface for G-Way remote OAuth discovery and browser linking."""

from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

from ..authorization import AuthorizationError
from ..dispatch import resolve_operation
from ..mutation import MutationError
from ..security.authentication import BearerAuthenticationError
from ..security.oauth import OAuthAuthenticationError, OAuthRegistry
from ..security.tokens import TokenRegistry
from ..tokens import tokenize
from .account import RemoteAccountApplication
from .metadata import RemoteOAuthMetadata
from .oauth import OAuthProtocolError, RemoteOAuthProtocol


MAX_QUERY_COMMAND_BYTES = 16 * 1024


class RemoteDiscoveryApplication:
    """Route only the standards discovery documents implemented by O1."""

    def __init__(self, metadata):
        if not isinstance(metadata, RemoteOAuthMetadata):
            raise TypeError("metadata must be RemoteOAuthMetadata")
        self.metadata = metadata
        acceptance_client_id = (
            metadata.issuer.rstrip("/") + "/.well-known/gway-acceptance-client"
        )
        self.routes = {
            "/.well-known/gway-acceptance-client": (
                200,
                lambda: {
                    "client_id": acceptance_client_id,
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                    "token_endpoint_auth_methods": ["none"],
                },
            ),
            metadata.protected_resource_metadata_path: (
                200,
                metadata.protected_resource_document,
            ),
            metadata.authorization_server_metadata_path: (
                200,
                metadata.authorization_server_document,
            ),
            "/oauth/authorize": (501, lambda: {"error": "not_implemented"}),
            "/oauth/token": (501, lambda: {"error": "not_implemented"}),
            "/oauth/revoke": (501, lambda: {"error": "not_implemented"}),
        }

    def response(self, method, path, *, headers=None, body=b""):
        del headers, body
        if str(method).upper() != "GET":
            return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
        path = str(path).partition("?")[0]
        route = self.routes.get(path)
        if route is None:
            return 404, {}, {"error": "not_found"}
        status, handler = route
        return status, {"content-type": "application/json"}, handler()


class RemoteApplication(RemoteDiscoveryApplication):
    """Discovery plus O2 browser session, bearer linking, and consent."""

    cookie_name = "gway_remote_session"

    def __init__(
        self,
        metadata,
        *,
        account=None,
        client_resolver=None,
        runtime=None,
    ):
        super().__init__(metadata)
        self.runtime = runtime
        self._query_lock = threading.RLock()
        if account is None and runtime is not None:
            oauth = OAuthRegistry(runtime.security_path)
            def resolve_runtime_operation(name):
                try:
                    resolution = resolve_operation(runtime, tokenize(str(name)))
                except LookupError:
                    return None
                return resolution.callable

            account = RemoteAccountApplication(
                oauth=oauth,
                tokens=TokenRegistry(runtime.security_path),
                operation_resolver=resolve_runtime_operation,
            )
        self.account = RemoteAccountApplication() if account is None else account
        self.oauth = RemoteOAuthProtocol(
            metadata,
            self.account,
            client_resolver=client_resolver,
            default_scope="chatgpt-logs",
        )
        self.oauth_by_resource = {metadata.resource: self.oauth}
        authorization_document = metadata.authorization_server_document()
        authorization_document["protected_resources"] = sorted(self.oauth_by_resource)
        authorization_document["scopes_supported"] = sorted(
            {
                scope
                for protocol in self.oauth_by_resource.values()
                for scope in protocol.metadata.scopes_supported
            }
        )
        self.routes[metadata.authorization_server_metadata_path] = (
            200,
            lambda: authorization_document,
        )

        self.browser = None
        if runtime is not None:
            from .browser import compose as compose_browser

            self.browser = compose_browser(runtime, self)

    def _cookie(self, headers):
        value = (headers or {}).get("cookie", "")
        cookie = SimpleCookie()
        cookie.load(value)
        morsel = cookie.get(self.cookie_name)
        return None if morsel is None else morsel.value

    def _session(self, headers, *, create=False):
        session = self.account.sessions.get(self._cookie(headers))
        created = False
        if session is None and create:
            session = self.account.new_session()
            created = True
        return session, created

    def _cookie_header(self, session):
        parts = [
            f"{self.cookie_name}={session.id}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            "Max-Age=1800",
        ]
        if urlsplit(self.metadata.issuer).scheme == "https":
            parts.append("Secure")
        return "; ".join(parts)

    @staticmethod
    def _form(body):
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parsed = parse_qs(str(body), keep_blank_values=True)
        return {name: values[-1] for name, values in parsed.items()}

    @staticmethod
    def _html(status, body, headers=None):
        result = {"content-type": "text/html; charset=utf-8"}
        result.update(headers or {})
        return status, result, body

    @staticmethod
    def _redirect(location, headers=None):
        result = {"location": location}
        result.update(headers or {})
        return 303, result, ""

    def _with_cookie(self, headers, session, created):
        if created:
            headers = dict(headers)
            headers["set-cookie"] = self._cookie_header(session)
        return headers

    def _oauth_for_resource(self, params):
        params = {} if params is None else params
        resource = str(params.get("resource") or "").strip()

        if not resource:
            try:
                grant_type = str(params.get("grant_type") or "").strip()
                if grant_type == "authorization_code":
                    resource = self.account.oauth.authorization_code_resource(
                        params.get("code")
                    )
                elif grant_type == "refresh_token":
                    resource = self.account.oauth.refresh_token_resource(
                        params.get("refresh_token")
                    )
            except OAuthAuthenticationError as error:
                raise OAuthProtocolError("invalid_grant") from error

        if resource:
            params["resource"] = resource
        protocol = self.oauth_by_resource.get(resource)
        if protocol is None:
            raise OAuthProtocolError("invalid_target")
        return protocol

    @staticmethod
    def _bearer(headers):
        authorization = (headers or {}).get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not credential.strip():
            raise BearerAuthenticationError()
        return credential.strip()

    def _query(self, method, split, headers):
        response_headers = {
            "content-type": "application/json",
            "cache-control": "no-store",
            "pragma": "no-cache",
        }
        if method != "GET":
            return 405, {**response_headers, "allow": "GET"}, {
                "error": "method_not_allowed"
            }
        if self.runtime is None:
            return 503, response_headers, {"error": "query_unavailable"}

        params = parse_qs(split.query, keep_blank_values=True)
        values = params.get("c")
        if not values or not values[-1].strip():
            return 400, response_headers, {
                "error": "invalid_query",
                "message": "Query parameter 'c' is required",
            }
        command = values[-1]
        if len(command.encode("utf-8")) > MAX_QUERY_COMMAND_BYTES:
            return 400, response_headers, {
                "error": "query_too_large",
                "message": "Query command exceeds the maximum size",
            }

        try:
            bearer = self._bearer(headers)
            with self._query_lock:
                result = self.runtime.execute_authenticated(
                    bearer,
                    command,
                    resource=self.metadata.resource,
                    mutate=False,
                )
        except BearerAuthenticationError:
            return 401, {
                **response_headers,
                "www-authenticate": "Bearer",
            }, {"error": "invalid_bearer"}
        except AuthorizationError as error:
            return 403, response_headers, {
                "error": "not_authorized",
                "message": str(error),
            }
        except MutationError as error:
            return 409, response_headers, {
                "error": "mutation_not_allowed",
                "message": str(error),
            }
        except (LookupError, TypeError, ValueError) as error:
            return 400, response_headers, {
                "error": "invalid_command",
                "message": str(error),
            }

        return 200, response_headers, {"result": result}

    def response(self, method, path, *, headers=None, body=b""):
        method = str(method).upper()
        split = urlsplit(str(path))
        route = split.path
        headers = {str(k).casefold(): str(v) for k, v in (headers or {}).items()}

        if self.browser is not None:
            from ..appadapter import MethodNotAllowed, RouteNotFound
            from .browser import BrowserRequest

            request = BrowserRequest(
                method=method,
                path=str(path),
                headers=headers,
                application=self,
                body=body,
            )
            try:
                with self.runtime.request_scope():
                    return self.browser.request(
                        route,
                        method,
                        arguments={"request": request},
                    )
            except RouteNotFound:
                pass
            except MethodNotAllowed:
                allowed = ", ".join(
                    item.method for item in self.browser.app.routes
                    if item.route == route
                )
                return 405, {"allow": allowed}, {"error": "method_not_allowed"}

        if route == "/query":
            return self._query(method, split, headers)

        if route == "/oauth/authorize":
            if method not in {"GET", "POST"}:
                return 405, {"allow": "GET, POST"}, {"error": "method_not_allowed"}
            session, created = self._session(headers, create=True)
            params = (
                {name: values[-1] for name, values in parse_qs(
                    split.query, keep_blank_values=True
                ).items()}
                if method == "GET"
                else self._form(body)
            )
            try:
                self._oauth_for_resource(params).stage_authorization(session, params)
            except OAuthProtocolError as error:
                return error.status, {"content-type": "application/json"}, error.payload()
            response_headers = self._with_cookie({}, session, created)
            destination = "/consent" if session.link_name else "/connect"
            return self._redirect(destination, response_headers)

        if route == "/oauth/token":
            if method != "POST":
                return 405, {"allow": "POST"}, {"error": "method_not_allowed"}
            try:
                params = self._form(body)
                payload = self._oauth_for_resource(params).token(
                    params,
                    headers=headers,
                )
            except OAuthProtocolError as error:
                return error.status, {
                    "content-type": "application/json",
                    "cache-control": "no-store",
                    "pragma": "no-cache",
                }, error.payload()
            return 200, {
                "content-type": "application/json",
                "cache-control": "no-store",
                "pragma": "no-cache",
            }, payload

        if route == "/oauth/revoke":
            if method != "POST":
                return 405, {"allow": "POST"}, {"error": "method_not_allowed"}
            try:
                payload = self.oauth.revoke(self._form(body))
            except OAuthProtocolError as error:
                return error.status, {"content-type": "application/json"}, error.payload()
            return 200, {"content-type": "application/json"}, payload

        if route in self.routes:
            return super().response(method, path, headers=headers, body=body)

        if self.browser is not None:
            return 404, {}, {"error": "not_found"}

        if route == "/privacy":
            if method != "GET":
                return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
            return self._html(
                200,
                "<!doctype html><html><head><title>G-Way Remote Privacy Policy</title></head>"
                "<body><h1>G-Way Remote Privacy Policy</h1>"
                "<p>G-Way Remote provides authenticated access to G-Way commands for "
                "connected MCP clients.</p>"
                "<h2>Data processed</h2>"
                "<p>The service may process OAuth client identifiers, authorization "
                "codes, access and refresh tokens, G-Way command strings, and command "
                "results such as requested log output.</p>"
                "<h2>Purpose</h2>"
                "<p>Data is processed only to authenticate the connection, authorize "
                "requested G-Way operations, execute those operations, and return results.</p>"
                "<h2>Storage and retention</h2>"
                "<p>OAuth client registrations, grants, and token state are stored in the "
                "service security registry until revoked, expired, rotated, or deleted. "
                "Command requests and results are not intentionally stored by this privacy "
                 "page or the remote transport itself; operational service logs may retain "
                "limited request metadata needed for security and reliability.</p>"
                "<h2>Sharing</h2>"
                "<p>The service does not sell personal data. Data is shared only with the "
                "connected client as needed to provide the requested operation and with "
                "infrastructure providers required to operate the service.</p>"
                "<h2>Security</h2>"
                "<p>OAuth credentials are used for authentication and authorization. "
                "Users should not intentionally place passwords, private keys, or other "
                "secrets in G-Way commands or log output.</p>"
                "<h2>Contact and deletion</h2>"
                "<p>Connections and OAuth grants can be revoked through the service. "
                "For privacy questions or deletion requests, contact the operator of "
                "remote.arthexis.com.</p>"
                "<p>Last updated: 2026-09-24.</p>"
                "</body></html>",
            )

        if route == "/login":
            if method != "GET":
                return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
            return self._redirect("/connect")

        if route == "/":
            if method != "GET":
                return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
            session, created = self._session(headers, create=True)
            response_headers = self._with_cookie({}, session, created)
            return self._html(
                200,
                "<!doctype html><html><body><h1>G-Way Remote</h1>"
                '<p><a href="/connect">Connect G-Way</a></p>'
                '<p><a href="/settings/connections">Connections</a></p>'
                "</body></html>",
                response_headers,
            )

        if route == "/connect":
            session, created = self._session(headers, create=(method == "GET"))
            if session is None:
                return 401, {}, {"error": "session_required"}
            if method == "GET":
                response_headers = self._with_cookie({}, session, created)
                return self._html(
                    200,
                    self.account.connect_page(session),
                    response_headers,
                )
            if method != "POST":
                return 405, {"allow": "GET, POST"}, {"error": "method_not_allowed"}
            form = self._form(body)
            previous_id = session.id
            try:
                self.account.connect(
                    session,
                    csrf=form.get("csrf"),
                    bearer=form.get("bearer"),
                )
            except PermissionError as error:
                message = str(error)
                status = 403 if "CSRF" in message else 401
                return status, {}, {"error": "connection_failed"}
            destination = (
                "/consent"
                if session.pending_client_id and session.pending_scopes
                else "/settings/connections"
            )
            response_headers = {"set-cookie": self._cookie_header(session)}
            if previous_id == session.id:
                response_headers = {}
            return self._redirect(destination, response_headers)

        if route == "/consent":
            session, created = self._session(headers, create=(method == "GET"))
            if session is None:
                return 401, {}, {"error": "session_required"}

            query = parse_qs(split.query, keep_blank_values=True)
            if method == "GET" and ("client_id" in query or "scope" in query):
                try:
                    self.account.stage_consent(
                        session,
                        query.get("client_id", [""])[-1],
                        query.get("scope", [""])[-1],
                    )
                except ValueError:
                    return 400, {}, {"error": "invalid_consent_request"}

            if method == "GET":
                if not session.link_name:
                    response_headers = self._with_cookie({}, session, created)
                    return self._redirect("/connect", response_headers)
                try:
                    page = self.account.consent_page(session)
                except (PermissionError, ValueError, LookupError):
                    return 400, {}, {"error": "invalid_consent_request"}
                response_headers = self._with_cookie({}, session, created)
                return self._html(200, page, response_headers)

            if method != "POST":
                return 405, {"allow": "GET, POST"}, {"error": "method_not_allowed"}
            form = self._form(body)
            try:
                grant = self.account.decide_consent(
                    session,
                    csrf=form.get("csrf"),
                    decision=form.get("decision"),
                )
            except PermissionError:
                return 403, {}, {"error": "consent_failed"}
            except (ValueError, LookupError):
                return 400, {}, {"error": "invalid_consent_request"}

            if session.pending_redirect_uri:
                try:
                    protocol = self.oauth if grant is None else self.oauth_by_resource.get(
                        grant.resource
                    )
                    if protocol is None:
                        raise OAuthProtocolError("invalid_target")
                    destination = protocol.finish_authorization(session, grant)
                except OAuthProtocolError as error:
                    return error.status, {"content-type": "application/json"}, error.payload()
                return self._redirect(destination)

            if grant is None:
                return self._html(
                    200,
                    "<!doctype html><html><body><h1>Access denied</h1></body></html>",
                )
            return self._html(
                200,
                "<!doctype html><html><body><h1>Access approved</h1>"
                f"<p>Grant {grant.id} is ready for authorization-code issuance.</p>"
                "</body></html>",
            )

        if route == "/settings/connections":
            session, created = self._session(headers, create=(method == "GET"))
            if session is None:
                return 401, {}, {"error": "session_required"}
            if method == "GET":
                response_headers = self._with_cookie({}, session, created)
                return self._html(
                    200,
                    self.account.connections_page(session),
                    response_headers,
                )
            if method != "POST":
                return 405, {"allow": "GET, POST"}, {"error": "method_not_allowed"}
            form = self._form(body)
            if form.get("action") != "revoke":
                return 400, {}, {"error": "invalid_connection_action"}
            try:
                self.account.revoke_connection(session, csrf=form.get("csrf"))
            except PermissionError:
                return 403, {}, {"error": "connection_action_failed"}
            return self._redirect("/settings/connections")

        return 404, {}, {"error": "not_found"}


def _encode(payload, content_type):
    if isinstance(payload, bytes):
        return payload
    if content_type.startswith("application/json"):
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return str(payload).encode("utf-8")


def _handler(application):
    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            length = int(self.headers.get("content-length", "0") or 0)
            body = self.rfile.read(length) if length else b""
            status, headers, payload = application.response(
                self.command,
                self.path,
                headers=dict(self.headers.items()),
                body=body,
            )
            content_type = headers.get("content-type", "application/json")
            encoded = _encode(payload, content_type)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = _respond
        do_POST = _respond
        do_PUT = _respond
        do_DELETE = _respond

        def log_message(self, format, *args):
            return None

    return Handler


def build_server(
    host="127.0.0.1",
    port=8001,
    *,
    public_origin="https://remote.arthexis.com",
    resource_path="/mcp",
    allow_insecure_loopback=False,
    account=None,
    client_resolver=None,
    runtime=None,
):
    """Build the remote HTTP server without starting its lifecycle."""
    metadata = RemoteOAuthMetadata.from_origin(
        public_origin,
        resource_path=resource_path,
        scopes_supported=("chatgpt-logs",),
        allow_insecure_loopback=allow_insecure_loopback,
    )
    application = RemoteApplication(
        metadata,
        account=account,
        client_resolver=client_resolver,
        runtime=runtime,
    )
    return ThreadingHTTPServer((str(host), int(port)), _handler(application))


def serve(
    host="127.0.0.1",
    port=8001,
    *,
    public_origin="https://remote.arthexis.com",
    resource_path="/mcp",
    runtime=None,
):
    """Serve remote OAuth discovery and browser linking until stopped."""
    server = build_server(
        host,
        port,
        public_origin=public_origin,
        resource_path=resource_path,
        runtime=runtime,
    )
    try:
        return server.serve_forever()
    finally:
        server.server_close()
