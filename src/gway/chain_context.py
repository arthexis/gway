from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar

_CHAIN_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "gway_chain_context",
    default=None,
)


def current_chain_context() -> dict[str, object]:
    """Return a copy of the active invocation-local chain context."""
    context = _CHAIN_CONTEXT.get()
    return dict(context) if context is not None else {}


@contextmanager
def chain_context_scope():
    """Create and reliably restore one invocation-local chain context."""
    context: dict[str, object] = {}
    token = _CHAIN_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CHAIN_CONTEXT.reset(token)


def publish_chain_result(result: object) -> None:
    """Publish a completed stage result to the active chain context."""
    context = _CHAIN_CONTEXT.get()
    if context is None:
        return
    context["result"] = result
    if isinstance(result, Mapping):
        context.update(result)


__all__ = ["chain_context_scope", "current_chain_context", "publish_chain_result"]
