"""Semantic local MCP launcher backed by the maintained MCP server companion."""

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


def run():
    """Start the local MCP interface for a client-managed agent session.

    This is the stable launcher used by local MCP clients. Transport selection is
    intentionally an implementation detail; the maintained implementation uses
    stdio today and exposes the generic query and gway tools.
    """
    return _server().mcp.run(transport="stdio")
