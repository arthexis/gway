"""Lazy MCP sampler capability and semantic launch surface."""

from gway.sampler import run


def register(gateway):
    """Register semantic MCP entry points lazily on one Gateway."""

    def local():
        """Start the local MCP interface for a client-managed agent session.

        Stable MCP client configuration:

            command: gway
            args: ["mcp", "local"]

        The concrete transport is an implementation detail of the maintained
        sampler recipe.
        """
        return run(gateway, "mcp/local")

    def serve(
        host="127.0.0.1",
        port=8000,
        route="/mcp",
        endpoint="http://127.0.0.1:8000/mcp",
    ):
        """Run the maintained persistent MCP service on loopback by default."""
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
