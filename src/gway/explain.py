from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExplainStep:
    kind: str
    message: str
    data: Mapping[str, object] = field(default_factory=dict)


_trace: ContextVar[list[ExplainStep] | None] = ContextVar("gway_explain_trace", default=None)


def enabled() -> bool:
    return _trace.get() is not None


def record(kind: str, message: str, **data: object) -> None:
    trace = _trace.get()
    if trace is None:
        return
    trace.append(ExplainStep(kind=kind, message=message, data=dict(data)))


@contextmanager
def explain_scope(*, enabled: bool = True) -> Iterator[list[ExplainStep]]:
    trace: list[ExplainStep] = []
    token = _trace.set(trace if enabled else None)
    try:
        yield trace
    finally:
        _trace.reset(token)


def current_trace() -> tuple[ExplainStep, ...]:
    trace = _trace.get()
    if trace is None:
        return ()
    return tuple(trace)


def _format_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    return repr(value)


def render_trace(steps: Sequence[ExplainStep]) -> str:
    lines = ["Explain:"]
    for step in steps:
        detail = f"  {step.kind}: {step.message}"
        if step.data:
            fields = ", ".join(
                f"{key}={_format_value(value)}" for key, value in step.data.items()
            )
            detail = f"{detail} ({fields})"
        lines.append(detail)
    return "\n".join(lines)
