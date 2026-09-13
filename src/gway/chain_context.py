from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar

_CHAIN_CONTEXT: ContextVar[MutableMapping[str, object] | None] = ContextVar(
    "gway_chain_context",
    default=None,
)


def current_chain_context() -> dict[str, object]:
    """Return a copy of the active invocation-local chain context."""
    context = _CHAIN_CONTEXT.get()
    return dict(context) if context is not None else {}


@contextmanager
def chain_context_scope(context: MutableMapping[str, object] | None = None):
    """Activate and reliably restore one invocation-local chain context."""
    active: MutableMapping[str, object] = {} if context is None else context
    token = _CHAIN_CONTEXT.set(active)
    try:
        yield active
    finally:
        _CHAIN_CONTEXT.reset(token)


def publish_chain_result(result: object) -> None:
    """Publish a completed stage result to the active chain context."""
    context = _CHAIN_CONTEXT.get()
    if context is None:
        return
    if isinstance(result, Mapping):
        context.update(result)
    context["result"] = result


__all__ = ["chain_context_scope", "current_chain_context", "publish_chain_result"]
