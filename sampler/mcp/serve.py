"""Semantic persistent MCP launcher backed by the maintained MCP server companion."""

import importlib.util
from pathlib import Path


def _server():
    path = Path(__file__).with_name("server.py")
    spec = importlib.util.spec_from_file_location("_gway_mcp_server", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load maintained MCP server: {path}")
    module = importlib.util.module_from_spec(spec)
    module.__dict__["_gway_parent"] = _gway_parent
    spec.loader.exec_module(module)
    return module


def run(
    host="127.0.0.1",
    port=8000,
    route="/mcp",
    endpoint="http://127.0.0.1:8000/mcp",
):
    """Run the persistent MCP service with safe loopback defaults."""
    return _server().serve(
        host=host,
        port=int(port),
        path=route,
        endpoint=endpoint,
    )
