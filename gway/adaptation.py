"""Pipeline adaptation for GWAY operation composition."""

import inspect
from dataclasses import dataclass

from .binding import BoundCall


@dataclass(frozen=True)
class AdaptationPlan:
    """Deterministic plan for placing one pipeline result into a consumer."""

    rule: str
    parameter: str | None
    producer_subject: str | None
    consumer_subject: str | None


def _result_subject(runtime, value):
    """Return the semantic subject currently bound to this exact result object."""
    if runtime is None or not hasattr(runtime, "results"):
        return None

    return runtime.results.subject(value)


def _pipeline_args(value):
    """Return the positional bundle carried by one raw pipeline result."""
    return tuple(value) if isinstance(value, tuple) else (value,)


def plan_pipeline(runtime, func, value, *, args=(), kwargs=None) -> AdaptationPlan:
    """Plan raw pipeline transport without modifying explicit arguments."""
    if not callable(func):
        raise TypeError(f"{func!r} is not callable")

    args = tuple(args)
    kwargs = {} if kwargs is None else dict(kwargs)
    signature = inspect.signature(func)
    consumer_subject = getattr(func, "__gway_subject__", None)
    producer_subject = _result_subject(runtime, value)
    receiver = getattr(func, "__gway_receiver__", None)

    if receiver is not None and producer_subject == receiver:
        signature.bind_partial(*args, **kwargs)
        return AdaptationPlan(
            "receiver",
            None,
            producer_subject,
            consumer_subject,
        )

    pipeline_args = _pipeline_args(value)
    combined = (*pipeline_args, *args)

    try:
        signature.bind_partial(*combined, **kwargs)
    except TypeError as exc:
        raise TypeError(
            "Consumer cannot accept pipeline positional arguments"
        ) from exc

    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    first = positional[0].name if pipeline_args and positional else None
    return AdaptationPlan(
        "positional",
        first,
        producer_subject,
        consumer_subject,
    )


def apply_plan(func, plan, value, *, args=(), kwargs=None) -> BoundCall:
    """Apply an AdaptationPlan while preserving explicit arguments."""
    signature = inspect.signature(func)
    args = tuple(args)
    kwargs = {} if kwargs is None else dict(kwargs)

    if plan.rule == "receiver":
        signature.bind_partial(*args, **kwargs)
        return BoundCall(args, kwargs)

    if plan.rule != "positional":
        raise ValueError(f"Unknown pipeline adaptation rule: {plan.rule}")

    combined = (*_pipeline_args(value), *args)
    signature.bind_partial(*combined, **kwargs)
    return BoundCall(combined, kwargs)


def adapt_pipeline(runtime, func, value, *, args=(), kwargs=None) -> BoundCall:
    """Plan and apply raw pipeline transport for one consumer."""
    plan = plan_pipeline(runtime, func, value, args=args, kwargs=kwargs)
    return apply_plan(func, plan, value, args=args, kwargs=kwargs)
