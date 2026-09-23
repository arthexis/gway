"""Built-in semantic bindings for Gway-owned configuration."""

from ..bindings import env


def declarations():
    """Return built-in physical bindings for core semantic settings."""
    return {
        "cache.cache_dir": (env("CACHE_DIR"),),
        "user.data_dir": (env("DATA_DIR"),),
        "system.data_dir": (env("SYSTEM_DATA_DIR"),),
        "user.bin_dir": (env("BIN_DIR"),),
        "system.bin_dir": (env("SYSTEM_BIN_DIR"),),
        "log.source": (env("LOG_SOURCE"),),
        "mcp.remote.endpoint": (env("REMOTE_MCP_ENDPOINT"),),
        "mcp.endpoint": (env("MCP_ENDPOINT"),),
        "remote.endpoint": (env("REMOTE_ENDPOINT"),),
        "mcp.remote.public_origin": (env("REMOTE_MCP_PUBLIC_ORIGIN"),),
        "mcp.public_origin": (env("MCP_PUBLIC_ORIGIN"),),
        "remote.public_origin": (env("REMOTE_PUBLIC_ORIGIN"),),
    }


def register(gateway):
    """Register physical compatibility aliases for core semantic settings."""
    available = declarations()
    for semantic_key, bindings in available.items():
        gateway.bind(semantic_key, *bindings, replace=False)
    return tuple(available)
