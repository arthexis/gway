"""Pipeline adaptation for GWAY operation composition."""

import inspect
import types
import typing
from dataclasses import dataclass

from .binding import BoundCall


@dataclass(frozen=True)
class AdaptationPlan:
    """Deterministic plan for placing one pipeline value into a consumer."""

    rule: str
    parameter: str
    producer_subject: str | None
    consumer_subject: str | None


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


def plan_pipeline(runtime, func, value, *, args=(), kwargs=None) -> AdaptationPlan:
    """Plan where a pipeline result should bind without modifying arguments."""
    if not callable(func):
        raise TypeError(f"{func!r} is not callable")

    args = tuple(args)
    kwargs = {} if kwargs is None else dict(kwargs)
    signature = inspect.signature(func)
    available = _available_parameters(signature, args, kwargs)
    consumer_subject = getattr(func, "__gway_subject__", None)
    producer_subject = _result_subject(runtime, value)

    if consumer_subject:
        for parameter in available:
            if parameter.name == consumer_subject:
                return AdaptationPlan(
                    "consumer_subject",
                    parameter.name,
                    producer_subject,
                    consumer_subject,
                )

    if producer_subject:
        for parameter in available:
            if parameter.name == producer_subject:
                return AdaptationPlan(
                    "producer_subject",
                    parameter.name,
                    producer_subject,
                    consumer_subject,
                )

    for parameter in available:
        if _compatible(parameter.annotation, value):
            return AdaptationPlan(
                "annotation",
                parameter.name,
                producer_subject,
                consumer_subject,
            )

    for parameter in available:
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return AdaptationPlan(
                "positional",
                parameter.name,
                producer_subject,
                consumer_subject,
            )

    raise TypeError("Consumer has no available parameter for the pipeline value")


def apply_plan(func, plan, value, *, args=(), kwargs=None) -> BoundCall:
    """Apply an AdaptationPlan while preserving explicit arguments."""
    signature = inspect.signature(func)
    parameter = signature.parameters[plan.parameter]
    args = tuple(args)
    kwargs = {} if kwargs is None else dict(kwargs)

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
        raise TypeError(
            f"Cannot adapt pipeline value to positional-only parameter "
            f"{parameter.name!r}"
        )
    else:
        kwargs[parameter.name] = value

    bound = signature.bind_partial(*args, **kwargs)
    return BoundCall(bound.args, bound.kwargs)


def adapt_pipeline(runtime, func, value, *, args=(), kwargs=None) -> BoundCall:
    """Plan and apply pipeline adaptation for one consumer."""
    plan = plan_pipeline(runtime, func, value, args=args, kwargs=kwargs)
    return apply_plan(func, plan, value, args=args, kwargs=kwargs)
