"""FastMCP surface for native GWAY command execution."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import threading

from fastmcp import Context as _Context
from fastmcp import FastMCP as _FastMCP
from fastmcp.server.dependencies import get_http_headers as _get_http_headers


mcp = _FastMCP("GWAY")
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
        self.host = os.environ[_CALLBACK_ENV[0]]
        self.port = int(os.environ[_CALLBACK_ENV[1]])
        self.token = os.environ[_CALLBACK_ENV[2]]

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

    def execute_authenticated(self, bearer, command):
        return self._request(
            "gateway.execute_authenticated",
            bearer=bearer,
            command=command,
        )


def _parent():
    injected = globals().get("_gway_parent")
    if injected is not None:
        return injected
    if all(os.environ.get(name) for name in _CALLBACK_ENV):
        return _SocketParentGateway()
    raise RuntimeError("GWAY parent bridge is not configured")


def _callback_connection(stream, token):
    request = _recv_json(stream)
    if not secrets.compare_digest(str(request.get("token", "")), token):
        _send_json(stream, {"ok": False, "error": "Invalid MCP callback token"})
        return
    method = request.get("method")
    if method not in {"gateway.execute", "gateway.execute_authenticated"}:
        _send_json(stream, {"ok": False, "error": "Unsupported MCP callback method"})
        return
    try:
        if method == "gateway.execute_authenticated":
            result = _validate_result(
                _gway_parent.execute_authenticated(
                    request["bearer"],
                    request["command"],
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


@mcp.tool(run_in_thread=False)
def gway(command: str, ctx: _Context | None = None):
    """Execute one native GWAY command under the caller's active authorization."""
    parent = _parent()
    if ctx is not None and ctx.transport == "streamable-http":
        return _validate_result(
            parent.execute_authenticated(_bearer_from_http(), command)
        )
    return _validate_result(parent.execute(command))


def run_http(*, host="127.0.0.1", port=8000, path="/mcp"):
    """Run the GWAY MCP server over Streamable HTTP."""
    return mcp.run(
        transport="http",
        host=host,
        port=int(port),
        path=path,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    args = parser.parse_args()

    if args.transport == "http":
        run_http(host=args.host, port=args.port, path=args.path)
    else:
        mcp.run(transport="stdio")
