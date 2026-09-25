"""Recipe-composed browser/account surface for the remote service."""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from ..sampler import resolve as resolve_sampler


@dataclass(frozen=True)
class BrowserRequest:
    """One transport-neutral request delivered to a remote browser handler."""

    method: str
    path: str
    headers: dict[str, str]
    application: object
    body: bytes = b""

    @property
    def split(self):
        return urlsplit(self.path)


class BrowserController:
    """Keep remote browser behavior in Python while recipes own route topology."""

    def __init__(self, application):
        self.application = application

    def privacy(self, request: BrowserRequest):
        return self.application._html(
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

    def login(self, request: BrowserRequest):
        del request
        return self.application._redirect("/connect")

    def index(self, request: BrowserRequest):
        session, created = self.application._session(request.headers, create=True)
        response_headers = self.application._with_cookie({}, session, created)
        return self.application._html(
            200,
            "<!doctype html><html><body><h1>G-Way Remote</h1>"
            '<p><a href="/connect">Connect G-Way</a></p>'
            '<p><a href="/settings/connections">Connections</a></p>'
            "</body></html>",
            response_headers,
        )

    def connect(self, request: BrowserRequest):
        application = self.application
        session, created = application._session(
            request.headers,
            create=request.method == "GET",
        )
        if session is None:
            return 401, {}, {"error": "session_required"}
        if request.method == "GET":
            response_headers = application._with_cookie({}, session, created)
            return application._html(
                200,
                application.account.connect_page(session),
                response_headers,
            )

        form = application._form(request.body)
        previous_id = session.id
        try:
            application.account.connect(
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
        response_headers = {"set-cookie": application._cookie_header(session)}
        if previous_id == session.id:
            response_headers = {}
        return application._redirect(destination, response_headers)

    def consent(self, request: BrowserRequest):
        application = self.application
        session, created = application._session(
            request.headers,
            create=request.method == "GET",
        )
        if session is None:
            return 401, {}, {"error": "session_required"}

        query = parse_qs(request.split.query, keep_blank_values=True)
        if request.method == "GET" and ("client_id" in query or "scope" in query):
            try:
                application.account.stage_consent(
                    session,
                    query.get("client_id", [""])[-1],
                    query.get("scope", [""])[-1],
                )
            except ValueError:
                return 400, {}, {"error": "invalid_consent_request"}

        if request.method == "GET":
            if not session.link_name:
                response_headers = application._with_cookie({}, session, created)
                return application._redirect("/connect", response_headers)
            try:
                page = application.account.consent_page(session)
            except (PermissionError, ValueError, LookupError):
                return 400, {}, {"error": "invalid_consent_request"}
            response_headers = application._with_cookie({}, session, created)
            return application._html(200, page, response_headers)

        form = application._form(request.body)
        try:
            grant = application.account.decide_consent(
                session,
                csrf=form.get("csrf"),
                decision=form.get("decision"),
            )
        except PermissionError:
            return 403, {}, {"error": "consent_failed"}
        except (ValueError, LookupError):
            return 400, {}, {"error": "invalid_consent_request"}

        if session.pending_redirect_uri:
            from .oauth import OAuthProtocolError

            try:
                protocol = (
                    application.oauth
                    if grant is None
                    else application.oauth_by_resource.get(grant.resource)
                )
                if protocol is None:
                    raise OAuthProtocolError("invalid_target")
                destination = protocol.finish_authorization(session, grant)
            except OAuthProtocolError as error:
                return (
                    error.status,
                    {"content-type": "application/json"},
                    error.payload(),
                )
            return application._redirect(destination)

        if grant is None:
            return application._html(
                200,
                "<!doctype html><html><body><h1>Access denied</h1></body></html>",
            )
        return application._html(
            200,
            "<!doctype html><html><body><h1>Access approved</h1>"
            f"<p>Grant {grant.id} is ready for authorization-code issuance.</p>"
            "</body></html>",
        )

    def connections(self, request: BrowserRequest):
        application = self.application
        session, created = application._session(
            request.headers,
            create=request.method == "GET",
        )
        if session is None:
            return 401, {}, {"error": "session_required"}
        if request.method == "GET":
            response_headers = application._with_cookie({}, session, created)
            return application._html(
                200,
                application.account.connections_page(session),
                response_headers,
            )

        form = application._form(request.body)
        if form.get("action") != "revoke":
            return 400, {}, {"error": "invalid_connection_action"}
        try:
            application.account.revoke_connection(session, csrf=form.get("csrf"))
        except PermissionError:
            return 403, {}, {"error": "connection_action_failed"}
        return application._redirect("/settings/connections")


def compose(runtime, application):
    """Compose the maintained remote browser AppSpec and return its adapter."""
    operations = {
        "remote.browser.index": index,
        "remote.browser.login": login,
        "remote.browser.privacy": privacy,
        "remote.browser.connect": connect,
        "remote.browser.consent": consent,
        "remote.browser.connections": connections,
    }
    for name, handler in operations.items():
        runtime.wrap(name, handler)

    recipe = resolve_sampler("remote/browser")
    with runtime.request_scope():
        app = runtime(recipe)

    from ..sampler import load as load_sampler

    web_app = load_sampler("web/app")
    return web_app.InMemoryAdapter(runtime, app)


def index(request: BrowserRequest):
    return BrowserController(request.application).index(request)


def login(request: BrowserRequest):
    return BrowserController(request.application).login(request)


def privacy(request: BrowserRequest):
    return BrowserController(request.application).privacy(request)


def connect(request: BrowserRequest):
    return BrowserController(request.application).connect(request)


def consent(request: BrowserRequest):
    return BrowserController(request.application).consent(request)


def connections(request: BrowserRequest):
    return BrowserController(request.application).connections(request)
