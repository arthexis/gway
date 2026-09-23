"""Built-in semantic bindings for Gway-owned configuration."""

from ..bindings import env


def register(gateway):
    """Register physical compatibility aliases for core semantic settings."""
    declarations = {
        "cache.cache_dir": (env("CACHE_DIR"),),
        "log.source": (env("LOG_SOURCE"),),
        "mcp.remote.endpoint": (env("REMOTE_MCP_ENDPOINT"),),
        "mcp.endpoint": (env("MCP_ENDPOINT"),),
        "remote.endpoint": (env("REMOTE_ENDPOINT"),),
        "mcp.remote.public_origin": (env("REMOTE_MCP_PUBLIC_ORIGIN"),),
        "mcp.public_origin": (env("MCP_PUBLIC_ORIGIN"),),
        "remote.public_origin": (env("REMOTE_PUBLIC_ORIGIN"),),
    }
    for semantic_key, bindings in declarations.items():
        gateway.bind(semantic_key, *bindings, replace=False)
    return tuple(declarations)
