"""Semantic callable normalization for GWAY."""

import inspect

from .binding import BoundCall, Literal
from .sigil import Sigil, Spool


def complete_arguments(runtime, subject, func, args=(), kwargs=None) -> BoundCall:
    """Complete explicit Python arguments with semantic context and defaults."""
    kwargs = {} if kwargs is None else kwargs
    signature = inspect.signature(func)
    bound = signature.bind_partial(*args, **kwargs)

    call_args = []
    call_kwargs = {}

    for name, parameter in signature.parameters.items():
        if name in bound.arguments:
            value = bound.arguments[name]
        elif subject and name == subject:
            value = runtime.find_value(name)
            if value is None:
                value = parameter.default
        else:
            value = parameter.default

        if isinstance(value, (Sigil, Spool)):
            value = value.resolve(runtime)

        if value is inspect.Parameter.empty:
            raise TypeError(f"missing required argument: {name}")

        if isinstance(value, Literal):
            value = str(value)

        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            call_args.append(value)
        elif parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
            call_args.append(value)
        elif parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            call_args.extend(value)
        elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            call_kwargs[name] = value
        elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
            call_kwargs.update(value)

    return BoundCall(tuple(call_args), call_kwargs)
