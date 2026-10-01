"""FastMCP surface for native GWAY command execution."""

from contextlib import contextmanager
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import asyncio
import base64
import json
from pathlib import Path  # noqa: F401 - exposed to managed companion probes
import secrets
import shlex
import socket
import struct
import threading
import time
from urllib.parse import urlsplit
from fastmcp import FastMCP as _FastMCP
from fastmcp.dependencies import Progress
from fastmcp.tools import ToolResult
from fastmcp.tools.base import Tool
from fastmcp.server.auth import TokenVerifier as _TokenVerifier
from fastmcp.server.auth.auth import AccessToken as _AccessToken
from fastmcp.server.dependencies import get_http_headers as _get_http_headers
from fastmcp.server.dependencies import get_http_request as _get_http_request
from fastmcp.server.middleware import Middleware


_DEFAULT_PUBLIC_ORIGIN = "http://127.0.0.1:8000"

_TERMINAL_GITHUB_STATES = {
    "completed",
    "success",
    "failure",
    "cancelled",
    "canceled",
    "skipped",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
}


def _tail_stable(value):
    if isinstance(value, Mapping):
        return {
            str(key): _tail_stable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_tail_stable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def _tail_fingerprint(value):
    return json.dumps(
        _tail_stable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _tail_event(sequence, kind, operation, value, *, terminal=False):
    return {
        "sequence": sequence,
        "kind": kind,
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value": _tail_stable(value),
        "terminal": bool(terminal),
    }


def _tail_terminal(operation, value):
    words = tuple(
        word.casefold()
        for word in str(operation).replace(".", " ").replace("_", " ").split()
    )
    if len(words) < 2 or words[0] != "github":
        return False
    if words[1] not in {"check", "checks", "job", "jobs", "run", "runs"}:
        return False

    records = value if isinstance(value, list) else [value]
    if not records:
        return False
    for record in records:
        if not isinstance(record, Mapping):
            return False
        status = str(record.get("status") or "").casefold()
        conclusion = str(record.get("conclusion") or "").casefold()
        if (
            status not in _TERMINAL_GITHUB_STATES
            and conclusion not in _TERMINAL_GITHUB_STATES
        ):
            return False
    return True


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

    def list_operations(self):
        return self._request("gateway.list")

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
        "gateway.list",
        "gateway.execute",
        "gateway.authenticate_bearer",
        "gateway.execute_authenticated",
    }:
        _send_json(stream, {"ok": False, "error": "Unsupported MCP callback method"})
        return
    try:
        if method == "gateway.list":
            result = _validate_result(_gway_parent.list_operations())
        elif method == "gateway.authenticate_bearer":
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


def _live_operation_names(parent):
    """Return canonical operations registered in the authoritative parent."""
    listing = getattr(parent, "list_operations", None)
    if callable(listing):
        return frozenset(str(name) for name in listing())
    ops = getattr(parent, "ops", None)
    records = getattr(ops, "records", None)
    if callable(records):
        return frozenset(record.name for record in records())
    raise RuntimeError("Parent Gateway does not expose its live operation registry")


def _authorized_operation_names(parent, bearer, resource):
    """Intersect the bearer's exact authority with the live operation registry."""
    current = parent.execute_authenticated(
        bearer,
        "security scope current",
        resource,
        mutate=False,
    )
    authorized = frozenset(current.get("operations") or ())
    live = _live_operation_names(parent)
    if "__all__" in authorized:
        return tuple(sorted(live))
    return tuple(sorted(live.intersection(authorized)))


def _operation_tool(parent, bearer, resource, operation, *, read_only=False):
    """Build one ephemeral MCP tool for an exact authorized Gway operation."""

    def invoke(tokens: list[str] | None = None):
        values = [] if tokens is None else [str(value) for value in tokens]
        suffix = " ".join(shlex.quote(value) for value in values)
        command = operation if not suffix else f"{operation} {suffix}"
        return _tool_result(
            parent.execute_authenticated(
                bearer,
                command,
                resource,
            )
        )

    return Tool.from_function(
        invoke,
        name=operation,
        description=(
            f"Invoke the exact authorized GWAY operation `{operation}`. "
            "Pass CLI argument/flag tokens in order through `tokens`; each token "
            "is quoted before dispatch so it cannot introduce another command."
        ),
        output_schema=_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": bool(read_only),
            "destructiveHint": not bool(read_only),
            "openWorldHint": True,
        },
        run_in_thread=False,
    )


def _authorized_operation_tools(parent, bearer, resource):
    """Build the current per-bearer MCP surface from curated scope authority."""
    identity = parent.authenticate_bearer(bearer, resource)
    read_only = not identity.get("mutation_capable", True)
    return tuple(
        _operation_tool(
            parent,
            bearer,
            resource,
            operation,
            read_only=read_only,
        )
        for operation in _authorized_operation_names(parent, bearer, resource)
    )


class _CapabilityProjectionMiddleware(Middleware):
    """Project HTTP MCP tools directly from the authenticated bearer authority."""

    async def on_list_tools(self, context, call_next):
        if not _has_http_request():
            return await call_next(context)
        parent = _parent()
        bearer = _bearer_from_http()
        return _authorized_operation_tools(parent, bearer, _auth.resource)

    async def on_call_tool(self, context, call_next):
        if not _has_http_request():
            return await call_next(context)
        parent = _parent()
        bearer = _bearer_from_http()
        tools = {
            tool.name: tool
            for tool in _authorized_operation_tools(parent, bearer, _auth.resource)
        }
        tool = tools.get(context.message.name)
        if tool is None:
            raise PermissionError(
                f"MCP tool is not authorized for this bearer: {context.message.name}"
            )
        return await tool.run(arguments=context.message.arguments or {})


mcp.add_middleware(_CapabilityProjectionMiddleware())


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
    semicolons; each published statement contributes its final result, including
    null when an operation explicitly returns None. Leading -j/--json is
    idempotent; --timed enables parent diagnostics and --no-mutate narrows policy.
    Other leading globals are rejected. Use a dash only when the
    next stage should consume the previous raw result. Prefer maintained
    project/node recipes over manually reproducing their internals, investigate
    through query first when mutation is unnecessary, and use help <operation>
    for exact syntax.
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
    observations with semicolons; each published statement contributes its
    final result, including null when an operation explicitly returns None. Use
    a dash only when the next stage should consume the previous raw result.
    Leading -j/--json is idempotent; --timed enables parent diagnostics and
    --no-mutate narrows policy. Other leading globals are rejected.
    Use help <operation> for exact syntax and prefer maintained project/node
    recipes over manually reproducing their internals.
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


@mcp.tool(
    run_in_thread=False,
    output_schema=_OUTPUT_SCHEMA,
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
async def tail(
    command: str,
    interval: float = 2.0,
    timeout: float | None = None,
    progress: Progress = Progress(),
):
    """Stream changed read-only results until the operation naturally completes.

    GitHub check, job, and run status operations stop when they reach terminal
    state. Other operations continue until cancellation or timeout. Each changed
    snapshot is emitted as a JSON progress message and the last snapshot is
    returned as the normal tool result.
    """
    if not str(command).strip():
        raise ValueError("tail command cannot be empty")
    interval = float(interval)
    if interval < 0:
        raise ValueError("tail interval cannot be negative")
    if timeout is not None:
        timeout = float(timeout)
        if timeout < 0:
            raise ValueError("tail timeout cannot be negative")

    parent = _parent()
    bearer = _bearer_from_http() if _has_http_request() else None
    started = time.monotonic()
    previous = None
    observed = False
    sequence = 0
    value = None

    while True:
        if bearer is not None:
            value = parent.execute_authenticated(
                bearer,
                command,
                _auth.resource,
                mutate=False,
            )
        else:
            value = parent.execute(command, mutate=False)

        fingerprint = _tail_fingerprint(value)
        done = _tail_terminal(str(command), value)
        if not observed or fingerprint != previous or done:
            sequence += 1
            event = _tail_event(
                sequence,
                "complete" if done else "update",
                str(command),
                value,
                terminal=done,
            )
            await progress.set_message(
                json.dumps(event, allow_nan=False, separators=(",", ":"))
            )

        if done:
            return _tool_result(value)
        if timeout is not None and time.monotonic() - started >= timeout:
            sequence += 1
            event = _tail_event(
                sequence,
                "timeout",
                str(command),
                value,
                terminal=True,
            )
            await progress.set_message(
                json.dumps(event, allow_nan=False, separators=(",", ":"))
            )
            return _tool_result(value)

        observed = True
        previous = fingerprint
        if interval:
            await asyncio.sleep(interval)


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
