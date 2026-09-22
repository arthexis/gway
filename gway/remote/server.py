"""Minimal read-only HTTP surface for remote OAuth discovery."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from .metadata import RemoteOAuthMetadata


class RemoteDiscoveryApplication:
    """Route only the standards discovery documents implemented by O1."""

    def __init__(self, metadata):
        if not isinstance(metadata, RemoteOAuthMetadata):
            raise TypeError("metadata must be RemoteOAuthMetadata")
        self.metadata = metadata
        self.routes = {
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

    def response(self, method, path):
        if str(method).upper() != "GET":
            return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
        path = str(path).partition("?")[0]
        route = self.routes.get(path)
        if route is None:
            return 404, {}, {"error": "not_found"}
        status, handler = route
        return status, {"content-type": "application/json"}, handler()


def _handler(application):
    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            status, headers, payload = application.response(
                self.command,
                self.path,
            )
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
):
    """Build the remote discovery HTTP server without starting its lifecycle."""
    metadata = RemoteOAuthMetadata.from_origin(
        public_origin,
        resource_path=resource_path,
        allow_insecure_loopback=allow_insecure_loopback,
    )
    application = RemoteDiscoveryApplication(metadata)
    return ThreadingHTTPServer((str(host), int(port)), _handler(application))


def serve(
    host="127.0.0.1",
    port=8001,
    *,
    public_origin="https://remote.arthexis.com",
    resource_path="/mcp",
):
    """Serve OAuth discovery only; authorization flows arrive in later slices."""
    server = build_server(
        host,
        port,
        public_origin=public_origin,
        resource_path=resource_path,
    )
    try:
        return server.serve_forever()
    finally:
        server.server_close()
