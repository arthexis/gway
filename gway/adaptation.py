"""Pipeline adaptation for GWAY operation composition."""

import inspect

from .binding import BoundCall


def adapt_pipeline(func, value, *, args=(), kwargs=None) -> BoundCall:
    """Adapt a pipeline value to the consumer's first positional input.

    This intentionally preserves the current GWAY chaining rule. More semantic
    matching can evolve behind this boundary without changing dispatch callers.
    """
    if not callable(func):
        raise TypeError(f"{func!r} is not callable")

    kwargs = {} if kwargs is None else dict(kwargs)
    adapted_args = (value, *tuple(args))

    # Validate the current positional adaptation against the consumer signature.
    signature = inspect.signature(func)
    bound = signature.bind_partial(*adapted_args, **kwargs)
    return BoundCall(bound.args, bound.kwargs)
