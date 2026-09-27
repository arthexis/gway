"""Recipe-composed browser/account surface for the remote service."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
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
        del request
        return {}

    def login(self, request: BrowserRequest):
        del request
        return self.application._redirect("/connect")

    def index(self, request: BrowserRequest):
        session, created = self.application._session(request.headers, create=True)
        response_headers = self.application._with_cookie({}, session, created)
        return 200, response_headers, {}

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
            return 200, response_headers, application.account.connect_context(session)

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
                context = application.account.consent_context(session)
            except (PermissionError, ValueError, LookupError):
                return 400, {}, {"error": "invalid_consent_request"}
            response_headers = application._with_cookie({}, session, created)
            return 200, response_headers, context

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
            return 200, response_headers, application.account.connections_context(session)

        form = application._form(request.body)
        if form.get("action") != "revoke":
            return 400, {}, {"error": "invalid_connection_action"}
        try:
            application.account.revoke_connection(session, csrf=form.get("csrf"))
        except PermissionError:
            return 403, {}, {"error": "connection_action_failed"}
        return application._redirect("/settings/connections")


class BrowserRecipeAdapter:
    """Render recipe-owned Remote views around companion-provided context."""

    def __init__(self, gateway, app):
        from ..sampler import load as load_sampler

        self.gateway = gateway
        self.dispatch = load_sampler("web/app").InMemoryAdapter(gateway, app)

    @property
    def app(self):
        return self.dispatch.app

    @app.setter
    def app(self, value):
        self.dispatch.app = value

    def request(self, route, method="GET", arguments=None):
        mapping = self.dispatch.resolve(route, method)
        if mapping.static:
            path = Path(mapping.static)
            if not path.is_file():
                return 404, {}, {"error": "not_found"}
            headers = {}
            if mapping.content_type:
                headers["content-type"] = mapping.content_type
            return 200, headers, path.read_bytes()

        result = self.dispatch.invoke(mapping, arguments=arguments)
        if not mapping.template:
            return result

        from ..sampler import load as load_sampler

        render_template = load_sampler("web/app").server.render_template
        if (
            isinstance(result, tuple)
            and len(result) == 3
            and isinstance(result[0], int)
        ):
            status, headers, payload = result
            if status != 200 or not isinstance(payload, Mapping):
                return result
        else:
            status, headers, payload = 200, {}, result
            if not isinstance(payload, Mapping):
                return result

        rendered = render_template(
            self.gateway,
            self.app,
            mapping,
            str(method).upper(),
            payload,
        )
        headers = dict(headers or {})
        headers.setdefault("content-type", "text/html; charset=utf-8")
        return status, headers, rendered


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

    return BrowserRecipeAdapter(runtime, app)


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
