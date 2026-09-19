"""Semantic callable normalization for GWAY."""

import inspect

from .binding import BoundCall, Literal
from .sigil import Sigil, Spool


_MISSING = object()


def complete_arguments(
    runtime,
    subject,
    func,
    args=(),
    kwargs=None,
    *,
    receiver=None,
) -> BoundCall:
    """Complete explicit Python arguments with semantic context and defaults."""
    kwargs = {} if kwargs is None else kwargs
    signature = inspect.signature(func)
    args = tuple(args)

    if receiver is not None:
        value = runtime.find_value(receiver, _MISSING)
        if value is _MISSING:
            raise TypeError(f"missing semantic receiver: {receiver}")
        args = (value, *args)

    bound = signature.bind_partial(*args, **kwargs)

    call_args = []
    call_kwargs = {}

    for name, parameter in signature.parameters.items():
        if name in bound.arguments:
            value = bound.arguments[name]
        else:
            value = runtime.find_value(name, _MISSING)
            if value is _MISSING:
                value = parameter.default

        if value is inspect.Parameter.empty:
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                value = ()
            elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
                value = {}

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
