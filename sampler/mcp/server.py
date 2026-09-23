"""FastMCP surface for native GWAY command execution."""

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import socket
import struct
import threading
from urllib.parse import urlsplit

from fastmcp import FastMCP as _FastMCP
from gway.environment import process_environment
from fastmcp.server.auth import TokenVerifier as _TokenVerifier
from fastmcp.server.auth.auth import AccessToken as _AccessToken
from fastmcp.server.dependencies import get_http_headers as _get_http_headers
from fastmcp.server.dependencies import get_http_request as _get_http_request


_DEFAULT_PUBLIC_ORIGIN = "http://127.0.0.1:8000"


class _GwayTokenVerifier(_TokenVerifier):
    """Delegate MCP bearer validation to the authoritative parent Gateway."""

    def __init__(self):
        super().__init__(
            base_url=process_environment.get(
                "GWAY_MCP_PUBLIC_ORIGIN",
                _DEFAULT_PUBLIC_ORIGIN,
            )
        )
        self.mcp_path = "/mcp"

    def configure(self, *, public_origin=None, path="/mcp"):
        if public_origin is not None:
            self.base_url = str(public_origin).rstrip("/")
        self.mcp_path = "/" + str(path).strip().strip("/")
        return self

    def get_routes(self, mcp_path=None):
        self.mcp_path = mcp_path or self.mcp_path
        self.set_mcp_path(self.mcp_path)
        return []

    @property
    def resource(self):
        return str(self._get_resource_url(self.mcp_path)).rstrip("/")

    async def verify_token(self, token):
        try:
            identity = _parent().authenticate_bearer(token, self.resource)
        except Exception:
            return None
        return _AccessToken(
            token=token,
            client_id=identity["client_id"],
            scopes=list(identity["scopes"]),
            expires_at=None,
            claims={
                "sub": identity["principal"],
                "gway_kind": identity["kind"],
            },
        )


_auth = _GwayTokenVerifier()
mcp = _FastMCP("GWAY", auth=_auth)
_FRAME = struct.Struct("!I")
_CALLBACK_ENV = (
    "GWAY_MCP_CALLBACK_HOST",
    "GWAY_MCP_CALLBACK_PORT",
    "GWAY_MCP_CALLBACK_TOKEN",
)


def _validate_result(value):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exception:
        raise TypeError(
            f"GWAY result is not MCP-serializable: {type(value).__name__}"
        ) from exception
    return value


def _send_json(stream, value):
    payload = json.dumps(value, allow_nan=False).encode("utf-8")
    stream.sendall(_FRAME.pack(len(payload)) + payload)


def _recv_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise EOFError("MCP callback channel closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_json(stream):
    size = _FRAME.unpack(_recv_exact(stream, _FRAME.size))[0]
    return json.loads(_recv_exact(stream, size).decode("utf-8"))


class _SocketParentGateway:
    """Parent-Gateway proxy used by a standalone stdio MCP subprocess."""

    def __init__(self):
        self.host = process_environment[_CALLBACK_ENV[0]]
        self.port = int(process_environment[_CALLBACK_ENV[1]])
        self.token = process_environment[_CALLBACK_ENV[2]]

    def _request(self, method, **params):
        with socket.create_connection((self.host, self.port), timeout=10) as stream:
            _send_json(
                stream,
                {
                    "token": self.token,
                    "method": method,
                    **params,
                },
            )
            response = _recv_json(stream)
        if not response.get("ok"):
            raise RuntimeError(response.get("error") or "Parent Gateway request failed")
        return response.get("result")

    def execute(self, command):
        return self._request("gateway.execute", command=command)

    def authenticate_bearer(self, bearer, resource=None):
        return self._request(
            "gateway.authenticate_bearer",
            bearer=bearer,
            resource=resource,
        )

    def execute_authenticated(self, bearer, command, resource=None):
        return self._request(
            "gateway.execute_authenticated",
            bearer=bearer,
            command=command,
            resource=resource,
        )


def _parent():
    injected = globals().get("_gway_parent")
    if injected is not None:
        return injected
    if all(process_environment.get(name) for name in _CALLBACK_ENV):
        return _SocketParentGateway()
    raise RuntimeError("GWAY parent bridge is not configured")


def _callback_connection(stream, token):
    request = _recv_json(stream)
    if not secrets.compare_digest(str(request.get("token", "")), token):
        _send_json(stream, {"ok": False, "error": "Invalid MCP callback token"})
        return
    method = request.get("method")
    if method not in {
        "gateway.execute",
        "gateway.authenticate_bearer",
        "gateway.execute_authenticated",
    }:
        _send_json(stream, {"ok": False, "error": "Unsupported MCP callback method"})
        return
    try:
        if method == "gateway.authenticate_bearer":
            result = _validate_result(
                _gway_parent.authenticate_bearer(
                    request["bearer"],
                    request.get("resource"),
                )
            )
        elif method == "gateway.execute_authenticated":
            result = _validate_result(
                _gway_parent.execute_authenticated(
                    request["bearer"],
                    request["command"],
                    request.get("resource"),
                )
            )
        else:
            result = _validate_result(_gway_parent.execute(request["command"]))
        response = {"ok": True, "result": result}
    except BaseException as exception:
        response = {
            "ok": False,
            "error": f"{type(exception).__name__}: {exception}",
        }
    _send_json(stream, response)


def _callback_loop(listener, token, stop):
    listener.settimeout(0.1)
    while not stop.is_set():
        try:
            stream, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with stream:
            _callback_connection(stream, token)


@contextmanager
def _callback_relay():
    """Expose the active companion parent bridge to one stdio MCP subprocess."""
    if globals().get("_gway_parent") is None:
        raise RuntimeError("Callback relay requires a managed companion parent bridge")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    token = secrets.token_urlsafe(32)
    stop = threading.Event()
    thread = threading.Thread(
        target=_callback_loop,
        args=(listener, token, stop),
        name="gway-mcp-callback",
        daemon=True,
    )
    thread.start()
    try:
        yield {
            _CALLBACK_ENV[0]: host,
            _CALLBACK_ENV[1]: str(port),
            _CALLBACK_ENV[2]: token,
        }
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=1)


def _bearer_from_http():
    headers = _get_http_headers(include={"authorization"})
    value = headers.get("authorization", "")
    scheme, separator, credential = value.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not credential.strip():
        raise PermissionError("Bearer authentication required")
    return credential.strip()


def _has_http_request():
    try:
        _get_http_request()
    except RuntimeError:
        return False
    return True


@mcp.tool(run_in_thread=False)
def gway(command: str):
    """Execute one native GWAY command under the caller's active authorization."""
    parent = _parent()
    if _has_http_request():
        return _validate_result(
            parent.execute_authenticated(
                _bearer_from_http(),
                command,
                _auth.resource,
            )
        )
    return _validate_result(parent.execute(command))


def _endpoint_origin(endpoint, path):
    if endpoint is None:
        return None
    parsed = urlsplit(str(endpoint))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("MCP endpoint must be an absolute HTTP(S) URL")
    endpoint_path = parsed.path or "/"
    normalized_path = "/" + str(path).strip().strip("/")
    if endpoint_path.rstrip("/") != normalized_path.rstrip("/"):
        raise ValueError(
            f"MCP endpoint path {endpoint_path!r} does not match local path "
            f"{normalized_path!r}"
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def run_http(
    *,
    host="127.0.0.1",
    port=8000,
    path="/mcp",
    endpoint=None,
    public_origin=None,
):
    """Run the GWAY MCP server over authenticated Streamable HTTP."""
    if endpoint is not None and public_origin is not None:
        raise ValueError("Use endpoint instead of public_origin, not both")
    if endpoint is not None:
        public_origin = _endpoint_origin(endpoint, path)
    _auth.configure(public_origin=public_origin, path=path)
    return mcp.run(
        transport="http",
        host=host,
        port=int(port),
        path=path,
    )


def serve(
    host="127.0.0.1",
    port=8000,
    path="/mcp",
    endpoint=None,
    public_origin=None,
):
    """Serve the maintained GWAY MCP endpoint until the supervisor stops it.

    Args:
        host: HTTP bind address. Defaults to loopback.
        port: HTTP listen port. Defaults to 8000.
        path: Streamable HTTP endpoint path. Defaults to /mcp.
    """
    return run_http(
        host=host,
        port=port,
        path=path,
        endpoint=endpoint,
        public_origin=public_origin,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    parser.add_argument(
        "--endpoint",
        default=process_environment.get("GWAY_MCP_ENDPOINT"),
    )
    parser.add_argument(
        "--public-origin",
        default=process_environment.get("GWAY_MCP_PUBLIC_ORIGIN"),
    )
    args = parser.parse_args()

    if args.transport == "http":
        run_http(
            host=args.host,
            port=args.port,
            path=args.path,
            endpoint=args.endpoint,
            public_origin=args.public_origin,
        )
    else:
        mcp.run(transport="stdio")
