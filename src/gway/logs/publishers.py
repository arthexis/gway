from __future__ import annotations

from contextvars import ContextVar

from .binding import PublisherBinding

_bindings: ContextVar[dict[str, PublisherBinding] | None] = ContextVar(
    "gway_log_publisher_bindings",
    default=None,
)


def set_binding(binding: PublisherBinding) -> None:
    """Activate one provider-supplied publisher binding for this process."""
    current = dict(_bindings.get() or {})
    current[binding.destination] = binding
    _bindings.set(current)


def clear_bindings() -> None:
    """Drop process-local publisher bindings without modifying persisted state."""
    _bindings.set({})


def binding_for(destination: str) -> PublisherBinding | None:
    return (_bindings.get() or {}).get(destination)


def publish(destination: str, run_id: str, data: bytes) -> bool:
    """Publish through the transport declared by the active provider binding."""
    binding = binding_for(destination)
    if binding is None or not data:
        return False
    transport = binding.configuration.get("transport")
    if transport == "http":
        from .http import publish as publish_http

        return publish_http(binding, run_id, data)
    return False


__all__ = ["binding_for", "clear_bindings", "publish", "set_binding"]
