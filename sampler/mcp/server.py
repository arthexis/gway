"""FastMCP surface for native GWAY command execution."""

from contextlib import contextmanager
import base64
import json
from pathlib import Path
import secrets
import socket
import struct
import threading
from urllib.parse import urlsplit
from fastmcp import FastMCP as _FastMCP
from fastmcp.tools import ToolResult
from fastmcp.server.auth import TokenVerifier as _TokenVerifier
from fastmcp.server.auth.auth import AccessToken as _AccessToken
from fastmcp.server.dependencies import get_http_headers as _get_http_headers
from fastmcp.server.dependencies import get_http_request as _get_http_request


_DEFAULT_PUBLIC_ORIGIN = "http://127.0.0.1:8000"


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "result": {},
        "result_type": {
            "type": "string",
            "enum": [
                "mapping",
                "sequence",
                "string",
                "number",
                "boolean",
                "null",
            ],
        },
        "output": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stream": {
                        "type": "string",
                        "enum": ["stdout", "stderr"],
                    },
                    "text": {"type": "string"},
                },
                "required": ["stream", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["ok", "result", "result_type", "output"],
    "additionalProperties": False,
}


class _GwayTokenVerifier(_TokenVerifier):
    """Delegate MCP bearer validation to the authoritative parent Gateway."""

    def __init__(self):
        super().__init__(base_url=_DEFAULT_PUBLIC_ORIGIN)
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
def _encode_parent_bridge(host, port, token):
    """Serialize one ephemeral parent-Gateway bridge bootstrap."""
    payload = json.dumps(
        {"host": str(host), "port": int(port), "token": str(token)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_parent_bridge(value):
    """Deserialize one ephemeral parent-Gateway bridge bootstrap."""
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(str(value).encode("ascii")).decode("utf-8")
        )
        host = str(payload["host"])
        port = int(payload["port"])
        token = str(payload["token"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exception:
        raise ValueError("Invalid parent-Gateway bridge bootstrap") from exception
    if not host or not token:
        raise ValueError("Invalid parent-Gateway bridge bootstrap")
    return host, port, token


def _validate_result(value):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exception:
        raise TypeError(
            f"GWAY result is not MCP-serializable: {type(value).__name__}"
        ) from exception
    return value


def _result_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, (list, tuple)):
        return "sequence"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    raise TypeError(
        f"GWAY result has no MCP envelope type: {type(value).__name__}"
    )


def _envelope(value):
    value = _validate_result(value)
    return {
        "ok": True,
        "result": value,
        "result_type": _result_type(value),
        "output": [],
    }


def _content_text(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, allow_nan=False, separators=(",", ":"))


def _tool_result(value):
    value = _validate_result(value)
    return ToolResult(
        content=_content_text(value),
        structured_content=_envelope(value),
    )


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
    """Parent-Gateway capability transported to a standalone subprocess."""

    def __init__(self, host, port, token):
        self.host = str(host)
        self.port = int(port)
        self.token = str(token)

    @classmethod
    def from_bootstrap(cls, bootstrap):
        return cls(*_decode_parent_bridge(bootstrap))

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

    def execute(self, command, mutate=None):
        params = {"command": command}
        if mutate is not None:
            params["mutate"] = mutate
        return self._request("gateway.execute", **params)

    def authenticate_bearer(self, bearer, resource=None):
        return self._request(
            "gateway.authenticate_bearer",
            bearer=bearer,
            resource=resource,
        )

    def execute_authenticated(self, bearer, command, resource=None, mutate=None):
        params = {
            "bearer": bearer,
            "command": command,
            "resource": resource,
        }
        if mutate is not None:
            params["mutate"] = mutate
        return self._request("gateway.execute_authenticated", **params)


def _parent():
    injected = globals().get("_gway_parent")
    if injected is not None:
        return injected
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
            kwargs = {}
            if "mutate" in request:
                kwargs["mutate"] = request["mutate"]
            result = _validate_result(
                _gway_parent.execute_authenticated(
                    request["bearer"],
                    request["command"],
                    request.get("resource"),
                    **kwargs,
                )
            )
        else:
            kwargs = {}
            if "mutate" in request:
                kwargs["mutate"] = request["mutate"]
            result = _validate_result(
                _gway_parent.execute(request["command"], **kwargs)
            )
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
        yield _encode_parent_bridge(host, port, token)
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


@mcp.tool(
    run_in_thread=False,
    output_schema=_OUTPUT_SCHEMA,
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": True,
    },
)
def gway(command: str):
    """Execute authorized GWAY commands, including state changes.

    Use this tool when mutation is required. Combine independent commands with
    semicolons; each statement contributes its final non-null result. Use a
    dash only when the next stage should consume the previous raw result.
    Prefer maintained project/node recipes over manually reproducing their
    internals, and investigate through query first when mutation is
    unnecessary. Use guide <task> before broad exploration and
    help <operation> for exact syntax, including when guide recommends an
    external capability instead.
    """
    parent = _parent()
    if _has_http_request():
        return _tool_result(
            parent.execute_authenticated(
                _bearer_from_http(),
                command,
                _auth.resource,
            )
        )
    return _tool_result(parent.execute(command))


@mcp.tool(
    run_in_thread=False,
    output_schema=_OUTPUT_SCHEMA,
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
def query(command: str):
    """Investigate GWAY state with mutation disabled.

    Prefer this tool for observation and diagnosis. Combine independent
    observations with semicolons; each statement contributes its final
    non-null result. Use a dash only when the next stage should consume the
    previous raw result. Use guide <task> before broad exploratory probing and
    help <operation> for exact syntax. Prefer project/node-maintained recipes
    when guide recommends them, and honor recommendations to use an external
    capability instead of GWAY.
    """
    parent = _parent()
    if _has_http_request():
        return _tool_result(
            parent.execute_authenticated(
                _bearer_from_http(),
                command,
                _auth.resource,
                mutate=False,
            )
        )
    return _tool_result(parent.execute(command, mutate=False))


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
    parser.add_argument("--endpoint")
    parser.add_argument("--public-origin")
    parser.add_argument("--parent-bridge", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.parent_bridge:
        _gway_parent = _SocketParentGateway.from_bootstrap(args.parent_bridge)

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
