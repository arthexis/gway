"""Generic HTTP serving boundary for framework-neutral AppSpecs."""

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, unquote, urlsplit

from .appadapter import InMemoryAdapter
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


class RequestBindingError(ValueError):
    """Raised when declared HTTP inputs cannot be bound to a handler."""


def _match_path(pattern, path):
    """Match one route pattern and return named segment values."""
    if pattern == path:
        return {}
    pattern_parts = pattern.strip("/").split("/") if pattern != "/" else []
    path_parts = path.strip("/").split("/") if path != "/" else []
    if len(pattern_parts) != len(path_parts):
        return None

    values = {}
    for expected, actual in zip(pattern_parts, path_parts):
        if expected.startswith("{") and expected.endswith("}") and len(expected) > 2:
            name = expected[1:-1]
            values[name] = unquote(actual)
            continue
        if expected != actual:
            return None
    return values


def _body_value(request):
    """Decode the request body according to its declared content type."""
    if not request.body:
        return None
    content_type = request.headers.get("content-type", "").partition(";")[0].strip()
    if content_type == "application/json":
        try:
            return json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestBindingError("invalid JSON request body") from error
    if content_type.startswith("text/"):
        try:
            return request.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RequestBindingError("invalid UTF-8 request body") from error
    return request.body


def _binding_arguments(mapping, request, path_values):
    """Extract only recipe-declared HTTP inputs into handler arguments."""
    arguments = {}
    query = parse_qs(request.split.query, keep_blank_values=True)
    body_bindings = tuple(
        binding for binding in mapping.bindings if binding.source == "body"
    )
    decoded_body = _body_value(request) if body_bindings else None

    for binding in mapping.bindings:
        if binding.source == "query":
            values = query.get(binding.key)
            if values:
                arguments[binding.name] = values[-1]
        elif binding.source == "path":
            if binding.key in path_values:
                arguments[binding.name] = path_values[binding.key]
        elif binding.source == "header":
            key = binding.key.casefold()
            if key in request.headers:
                arguments[binding.name] = request.headers[key]
        elif binding.source == "body":
            if len(body_bindings) == 1:
                if decoded_body is not None:
                    arguments[binding.name] = decoded_body
            elif isinstance(decoded_body, dict) and binding.key in decoded_body:
                arguments[binding.name] = decoded_body[binding.key]
            elif decoded_body is not None and not isinstance(decoded_body, dict):
                raise RequestBindingError(
                    "multiple body bindings require a JSON object"
                )
    return arguments


class ApplicationHTTPAdapter:
    """Expose an AppSpec through a small framework-neutral HTTP response surface."""

    def __init__(self, gateway, app: AppSpec, *, context=None):
        if not isinstance(app, AppSpec):
            raise TypeError("HTTP adapter requires an AppSpec")
        self.gateway = gateway
        self.app = app
        self.dispatch = InMemoryAdapter(gateway, app)
        self.context = (
            dict(gateway.context)
            if context is None
            else dict(context)
        )

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

        matches = []
        for mapping in self.app.routes:
            values = _match_path(mapping.route, request.split.path)
            if values is not None:
                exact = mapping.route == request.split.path
                matches.append((not exact, mapping, values))
        matches.sort(key=lambda item: item[0])
        matches = [
            (mapping, values)
            for _, mapping, values in matches
        ]

        if not matches:
            return 404, {}, {"error": "not_found"}

        selected = next(
            (
                (mapping, values)
                for mapping, values in matches
                if mapping.method == request.method
            ),
            None,
        )
        if selected is None:
            allowed = ", ".join(mapping.method for mapping, _ in matches)
            return 405, {"allow": allowed}, {"error": "method_not_allowed"}

        mapping, path_values = selected
        try:
            arguments = _binding_arguments(mapping, request, path_values)
            with self.gateway.request_scope(context=context):
                result = self.dispatch.invoke(
                    mapping,
                    arguments=arguments,
                )
        except RequestBindingError as error:
            return 400, {}, {
                "error": "invalid_request",
                "message": str(error),
            }
        except TypeError as error:
            if "missing required argument:" not in str(error):
                raise
            return 400, {}, {
                "error": "invalid_request",
                "message": str(error),
            }

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
