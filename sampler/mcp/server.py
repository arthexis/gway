"""FastMCP surface for native GWAY command execution."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import threading

from fastmcp import FastMCP as _FastMCP


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

    def execute(self, command):
        with socket.create_connection((self.host, self.port), timeout=10) as stream:
            _send_json(
                stream,
                {
                    "token": self.token,
                    "method": "gateway.execute",
                    "command": command,
                },
            )
            response = _recv_json(stream)
        if not response.get("ok"):
            raise RuntimeError(response.get("error") or "Parent Gateway request failed")
        return response.get("result")


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
    if request.get("method") != "gateway.execute":
        _send_json(stream, {"ok": False, "error": "Unsupported MCP callback method"})
        return
    try:
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


@mcp.tool(run_in_thread=False)
def gway(command: str):
    """Execute one native GWAY command under the caller's active authorization."""
    return _validate_result(_parent().execute(command))


if __name__ == "__main__":
    mcp.run(transport="stdio")
