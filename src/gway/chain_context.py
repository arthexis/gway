from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar

from .provenance import ValueProvenance

_CHAIN_CONTEXT: ContextVar[MutableMapping[str, object] | None] = ContextVar(
    "gway_chain_context",
    default=None,
)
_CHAIN_PROVENANCE: ContextVar[MutableMapping[str, ValueProvenance] | None] = ContextVar(
    "gway_chain_provenance",
    default=None,
)


def current_chain_context() -> dict[str, object]:
    """Return a copy of the active invocation-local chain context."""
    context = _CHAIN_CONTEXT.get()
    return dict(context) if context is not None else {}


def current_chain_provenance() -> dict[str, ValueProvenance]:
    """Return a copy of provenance attached to the active named context."""
    provenance = _CHAIN_PROVENANCE.get()
    return dict(provenance) if provenance is not None else {}


@contextmanager
def chain_context_scope(
    context: MutableMapping[str, object] | None = None,
    provenance: MutableMapping[str, ValueProvenance] | None = None,
):
    """Activate and reliably restore one invocation-local chain context."""
    active: MutableMapping[str, object] = {} if context is None else context
    active_provenance: MutableMapping[str, ValueProvenance] = (
        {} if provenance is None else provenance
    )
    context_token = _CHAIN_CONTEXT.set(active)
    provenance_token = _CHAIN_PROVENANCE.set(active_provenance)
    try:
        yield active
    finally:
        _CHAIN_PROVENANCE.reset(provenance_token)
        _CHAIN_CONTEXT.reset(context_token)


def publish_chain_result(
    result: object,
    *,
    provenance: ValueProvenance | None = None,
) -> None:
    """Publish a completed stage result and producer metadata to active context."""
    context = _CHAIN_CONTEXT.get()
    if context is None:
        return
    named_provenance = _CHAIN_PROVENANCE.get()
    if isinstance(result, Mapping):
        context.update(result)
        if named_provenance is not None and provenance is not None:
            named_provenance.update((str(key), provenance) for key in result)
    context["result"] = result
    if named_provenance is not None and provenance is not None:
        named_provenance["result"] = provenance


__all__ = [
    "chain_context_scope",
    "current_chain_context",
    "current_chain_provenance",
    "publish_chain_result",
]
