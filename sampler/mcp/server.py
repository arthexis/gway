"""FastMCP surface for native GWAY command execution."""

import json

from fastmcp import FastMCP as _FastMCP


mcp = _FastMCP("GWAY")


def _validate_result(value):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exception:
        raise TypeError(
            f"GWAY result is not MCP-serializable: {type(value).__name__}"
        ) from exception
    return value


@mcp.tool(run_in_thread=False)
def gway(command: str):
    """Execute one native GWAY command under the caller's active authorization."""
    return _validate_result(_gway_parent.execute(command))
