"""Generic HTTP serving boundary for framework-neutral AppSpecs."""

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from .appadapter import InMemoryAdapter, MethodNotAllowed, RouteNotFound
from .appspec import AppSpec


@dataclass(frozen=True)
class ApplicationRequest:
    """Transport-neutral HTTP request exposed through Gway semantic context."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes = b""

    @property
    def split(self):
        return urlsplit(self.path)


class ApplicationHTTPAdapter:
    """Expose an AppSpec through a small framework-neutral HTTP response surface."""

    def __init__(self, gateway, app: AppSpec, *, context=None):
        if not isinstance(app, AppSpec):
            raise TypeError("HTTP adapter requires an AppSpec")
        self.gateway = gateway
        self.app = app
        self.dispatch = InMemoryAdapter(gateway, app)
        self.context = {} if context is None else dict(context)

    def response(self, method, path, *, headers=None, body=b""):
        """Dispatch one HTTP request through the composed application."""
        request = ApplicationRequest(
            method=str(method).upper(),
            path=str(path),
            headers={
                str(name).casefold(): str(value)
                for name, value in (headers or {}).items()
            },
            body=body,
        )
        context = dict(self.context)
        context["request"] = request

        try:
            with self.gateway.request_scope(context=context):
                result = self.dispatch.request(
                    request.split.path,
                    request.method,
                )
        except RouteNotFound:
            return 404, {}, {"error": "not_found"}
        except MethodNotAllowed:
            allowed = ", ".join(
                route.method
                for route in self.app.routes
                if route.route == request.split.path
            )
            return 405, {"allow": allowed}, {"error": "method_not_allowed"}

        return normalize_response(result)


def normalize_response(result):
    """Normalize an ordinary handler result to status, headers, payload."""
    if (
        isinstance(result, tuple)
        and len(result) == 3
        and isinstance(result[0], int)
    ):
        status, headers, payload = result
        return status, dict(headers or {}), payload
    if result is None:
        return 204, {}, b""
    return 200, {}, result


def _encode(payload, content_type=None):
    if isinstance(payload, bytes):
        return payload, content_type or "application/octet-stream"
    if isinstance(payload, str):
        return payload.encode("utf-8"), content_type or "text/plain; charset=utf-8"
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return encoded, content_type or "application/json"


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
            headers = {
                str(name).casefold(): str(value)
                for name, value in (headers or {}).items()
            }
            encoded, content_type = _encode(
                payload,
                headers.get("content-type"),
            )
            headers.setdefault("content-type", content_type)

            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(encoded)

        do_GET = _respond
        do_POST = _respond
        do_PUT = _respond
        do_PATCH = _respond
        do_DELETE = _respond
        do_HEAD = _respond

        def log_message(self, format, *args):
            return None

    return Handler


def build_server(application, host="127.0.0.1", port=0):
    """Build a threaded local HTTP server for an application response surface."""
    return ThreadingHTTPServer(
        (str(host), int(port)),
        _handler(application),
    )


def build_app_server(gateway, app, host="127.0.0.1", port=0, *, context=None):
    """Build a local HTTP server directly from an AppSpec."""
    application = ApplicationHTTPAdapter(
        gateway,
        app,
        context=context,
    )
    return build_server(application, host, port)


def serve_app(gateway, app, host="127.0.0.1", port=8000, *, context=None):
    """Serve an AppSpec in the foreground until the local server stops."""
    server = build_app_server(
        gateway,
        app,
        host,
        port,
        context=context,
    )
    try:
        return server.serve_forever()
    finally:
        server.server_close()
