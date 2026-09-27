"""Late-bound callable resolution for ingested Python operations."""

import inspect

from .mutation import public_signature


def resolve_callable(callable_obj):
    """Return the current implementation behind a Gway wrapper."""
    resolver = getattr(callable_obj, "__gway_callable_resolver__", None)
    if not callable(resolver):
        return callable_obj
    target = resolver()
    if not callable(target):
        raise TypeError("Resolved Gway operation target is not callable")
    return target


def callable_signature(callable_obj):
    """Return the current public signature for binding and documentation."""
    resolver = getattr(callable_obj, "__gway_callable_resolver__", None)
    if not callable(resolver):
        return inspect.signature(callable_obj)
    target = resolve_callable(callable_obj)
    signature = public_signature(
        target,
        receiver=getattr(callable_obj, "__gway_receiver__", None) is not None,
    )
    if signature is None:
        raise ValueError("Current Gway operation target has no inspectable signature")
    return signature
