"""Built-in semantic bindings for Gway-owned configuration."""

from ..bindings import env
from ..semantic import semantic_candidates


def declarations():
    """Return built-in physical bindings for core semantic settings."""
    return {
        "cache.cache_dir": (env("CACHE_DIR"),),
        "log.source": (env("LOG_SOURCE"),),
        "mcp.remote.endpoint": (env("REMOTE_MCP_ENDPOINT"),),
        "mcp.endpoint": (env("MCP_ENDPOINT"),),
        "remote.endpoint": (env("REMOTE_ENDPOINT"),),
        "mcp.remote.public_origin": (env("REMOTE_MCP_PUBLIC_ORIGIN"),),
        "mcp.public_origin": (env("MCP_PUBLIC_ORIGIN"),),
        "remote.public_origin": (env("REMOTE_PUBLIC_ORIGIN"),),
    }


def resolve(subject, *, topics=(), default=None):
    """Resolve one core semantic default without requiring a Gateway instance."""
    available = declarations()
    for candidate in semantic_candidates(subject, topics):
        for binding in available.get(candidate, ()):
            result = binding.resolve()
            if result.found:
                return result.value
    return default


def register(gateway):
    """Register physical compatibility aliases for core semantic settings."""
    available = declarations()
    for semantic_key, bindings in available.items():
        gateway.bind(semantic_key, *bindings, replace=False)
    return tuple(available)
