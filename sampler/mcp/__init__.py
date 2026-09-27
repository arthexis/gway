"""Lazy MCP sampler capability and semantic launch surface."""

from contextlib import contextmanager
import base64
import json
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import threading

from gway.recipe.environment import (
    environment_python,
    recipe_environment,
    sync_python_environment,
)
from gway.recipe.uv import ensure_uv


_FRAME = struct.Struct("!I")
_LOCAL_REQUIREMENTS = ("fastmcp>=4,<5",)


def _send_json(stream, value):
    payload = json.dumps(value, allow_nan=False).encode("utf-8")
    stream.sendall(_FRAME.pack(len(payload)) + payload)


def _recv_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise EOFError("MCP parent bridge closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_json(stream):
    size = _FRAME.unpack(_recv_exact(stream, _FRAME.size))[0]
    return json.loads(_recv_exact(stream, size).decode("utf-8"))


def _bridge_connection(gateway, stream, token):
    request = _recv_json(stream)
    if not secrets.compare_digest(str(request.get("token", "")), token):
        _send_json(stream, {"ok": False, "error": "Invalid MCP callback token"})
        return
    if request.get("method") != "gateway.execute":
        _send_json(stream, {"ok": False, "error": "Unsupported MCP callback method"})
        return
    try:
        kwargs = {}
        if "mutate" in request:
            kwargs["mutate"] = request["mutate"]
        result = gateway.execute(request["command"], **kwargs)
        response = {"ok": True, "result": result}
    except BaseException as exception:
        response = {
            "ok": False,
            "error": f"{type(exception).__name__}: {exception}",
        }
    _send_json(stream, response)


def _bridge_loop(gateway, listener, token, stop):
    listener.settimeout(0.1)
    while not stop.is_set():
        try:
            stream, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with stream:
            _bridge_connection(gateway, stream, token)


def _encode_bridge(host, port, token):
    payload = json.dumps(
        {"host": str(host), "port": int(port), "token": str(token)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


@contextmanager
def _parent_bridge(gateway):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    token = secrets.token_urlsafe(32)
    stop = threading.Event()
    thread = threading.Thread(
        target=_bridge_loop,
        args=(gateway, listener, token, stop),
        name="gway-mcp-local-bridge",
        daemon=True,
    )
    thread.start()
    try:
        yield _encode_bridge(host, port, token)
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=1)


def _local_python(gateway):
    recipe = Path(__file__).with_name("local.rx")
    environment = recipe_environment(gateway, recipe)
    system = environment.scope == "system"
    uv = ensure_uv(system=system, root=gateway.data_root(system=system))
    sync_python_environment(environment, uv, _LOCAL_REQUIREMENTS)
    return environment_python(environment)


def _run_local(gateway):
    """Run stdio MCP in its managed environment on the caller-facing descriptors."""
    python = _local_python(gateway)
    server = Path(__file__).with_name("server.py")
    with _parent_bridge(gateway) as bridge:
        completed = subprocess.run(
            [
                str(python),
                "-u",
                str(server),
                "--transport",
                "stdio",
                "--parent-bridge",
                bridge,
            ],
            check=True,
        )
    return completed.returncode


def register(gateway):
    """Register semantic MCP entry points lazily on one Gateway."""

    def local():
        """Start the local MCP interface for a client-managed agent session.

        Stable MCP client configuration:

            command: gway
            args: ["mcp", "local"]

        The maintained stdio server runs in its recipe-owned Python environment
        while inheriting the client-facing stdin/stdout of the top-level Gway
        process.
        """
        return _run_local(gateway)

    def serve(
        host="127.0.0.1",
        port: int = 8000,
        route="/mcp",
        endpoint="http://127.0.0.1:8000/mcp",
    ):
        """Run the maintained persistent MCP service on loopback by default."""
        from gway.sampler import run

        return run(
            gateway,
            "mcp/serve",
            host=host,
            port=port,
            route=route,
            endpoint=endpoint,
        )

    gateway.mcp_local = gateway.wrap(
        "mcp.local", local, op="mcp", sub="local"
    )
    gateway.mcp_serve = gateway.wrap(
        "mcp.serve", serve, op="mcp", sub="serve"
    )
    gateway.ops.register_alias("mcp.server", gateway.mcp_serve)
    return {"local": gateway.mcp_local, "serve": gateway.mcp_serve}


__all__ = ["register"]
