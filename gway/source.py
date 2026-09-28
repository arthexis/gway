"""Resolved operation source inspection."""

from dataclasses import asdict, dataclass
import inspect
from pathlib import Path


@dataclass(frozen=True)
class SourceDescriptor:
    """Stable source metadata for one resolved Gway operation."""

    operation: str
    kind: str
    source: str | None
    path: str | None
    start_line: int | None
    end_line: int | None
    available: bool = True
    reason: str | None = None

    def result(self):
        return asdict(self)


def _recipe_descriptor(operation, callable_):
    path = Path(callable_.__gway_source__).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exception:
        return SourceDescriptor(
            operation, "recipe", None, str(path), None, None, False, str(exception)
        )
    lines = text.splitlines()
    return SourceDescriptor(
        operation,
        "recipe",
        text,
        str(path),
        1,
        len(lines),
    )


def _python_descriptor(operation, callable_):
    target = inspect.unwrap(callable_)
    try:
        lines, start = inspect.getsourcelines(target)
        path = inspect.getsourcefile(target) or inspect.getfile(target)
    except (OSError, TypeError) as exception:
        return SourceDescriptor(
            operation,
            "python",
            None,
            None,
            None,
            None,
            False,
            str(exception),
        )
    text = "".join(lines)
    return SourceDescriptor(
        operation,
        "python",
        text,
        path,
        start,
        start + len(lines) - 1,
    )


def describe_resolved_source(resolution):
    """Describe source for exactly the callable selected by normal dispatch."""
    callable_ = resolution.callable
    operation = resolution.candidate.replace(".", " ")
    kind = getattr(callable_, "__gway_source_kind__", None)
    source = getattr(callable_, "__gway_source__", None)

    if kind == "recipe" and source is not None:
        return _recipe_descriptor(operation, callable_)
    return _python_descriptor(operation, callable_)


def inspect_source(gateway, *operation, mutate=False):
    """Return source metadata for the operation normal dispatch would execute."""
    del mutate
    if not operation:
        raise TypeError("source requires an operation")

    from .dispatch import resolve_operation
    from .tokens import tokenize

    resolution = resolve_operation(gateway, tokenize(" ".join(map(str, operation))))
    if resolution.arguments:
        raise LookupError(
            "source target includes unresolved arguments: "
            + " ".join(map(str, resolution.arguments))
        )
    return describe_resolved_source(resolution).result()
