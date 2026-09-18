"""Pipeline adaptation for GWAY operation composition."""

import inspect
import types
import typing

from .binding import BoundCall


def _result_subject(runtime, value):
    """Return the semantic subject currently bound to this exact result object."""
    if runtime is None or not hasattr(runtime, "results"):
        return None

    results = runtime.results.get_results()
    for subject, candidate in reversed(tuple(results.items())):
        if candidate is value:
            return subject
    return None


def _compatible(annotation, value):
    """Return whether a runtime value satisfies a concrete type annotation."""
    if annotation is inspect.Parameter.empty:
        return False

    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(_compatible(option, value) for option in typing.get_args(annotation))

    if origin is not None:
        annotation = origin

    try:
        return isinstance(value, annotation)
    except TypeError:
        return False


def _available_parameters(signature, args, kwargs):
    bound = signature.bind_partial(*args, **kwargs)
    return [
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in bound.arguments
        and parameter.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    ]


def _place_value(signature, parameter, value, args, kwargs):
    """Place a value without disturbing explicitly supplied arguments."""
    args = tuple(args)
    kwargs = dict(kwargs)

    positional = [
        item
        for item in signature.parameters.values()
        if item.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    consumed = len(args)

    if (
        parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and consumed < len(positional)
        and positional[consumed].name == parameter.name
    ):
        args = (*args, value)
    elif parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
        # Python cannot skip positional-only parameters.
        raise TypeError(
            f"Cannot adapt pipeline value to positional-only parameter "
            f"{parameter.name!r}"
        )
    else:
        kwargs[parameter.name] = value

    bound = signature.bind_partial(*args, **kwargs)
    return BoundCall(bound.args, bound.kwargs)


def adapt_pipeline(runtime, func, value, *, args=(), kwargs=None) -> BoundCall:
    """Adapt a pipeline result to the best available consumer parameter.

    Matching is deterministic: consumer semantic subject, producer subject name,
    compatible annotation, then the first available positional parameter.
    Explicit native arguments always remain authoritative.
    """
    if not callable(func):
        raise TypeError(f"{func!r} is not callable")

    args = tuple(args)
    kwargs = {} if kwargs is None else dict(kwargs)
    signature = inspect.signature(func)
    available = _available_parameters(signature, args, kwargs)

    consumer_subject = getattr(func, "__gway_subject__", None)
    if consumer_subject:
        for parameter in available:
            if parameter.name == consumer_subject:
                return _place_value(signature, parameter, value, args, kwargs)

    producer_subject = _result_subject(runtime, value)
    if producer_subject:
        for parameter in available:
            if parameter.name == producer_subject:
                return _place_value(signature, parameter, value, args, kwargs)

    for parameter in available:
        if _compatible(parameter.annotation, value):
            return _place_value(signature, parameter, value, args, kwargs)

    for parameter in available:
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return _place_value(signature, parameter, value, args, kwargs)

    raise TypeError("Consumer has no available parameter for the pipeline value")
