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


def search_descriptor(descriptor, query, *, context=2):
    """Search only within one already-resolved source descriptor."""
    if context < 0:
        raise ValueError("source search context must be non-negative")
    if not descriptor.available or descriptor.source is None:
        result = descriptor.result()
        result["matches"] = []
        result.pop("source", None)
        return result

    query = str(query)
    lines = descriptor.source.splitlines()
    first_line = descriptor.start_line or 1
    matches = []
    for index, line in enumerate(lines):
        if query not in line:
            continue
        before_start = max(0, index - context)
        after_end = min(len(lines), index + context + 1)
        matches.append(
            {
                "line": first_line + index,
                "text": line,
                "before": lines[before_start:index],
                "after": lines[index + 1 : after_end],
            }
        )

    return {
        "operation": descriptor.operation,
        "kind": descriptor.kind,
        "path": descriptor.path,
        "matches": matches,
    }


def inspect_source(
    gateway,
    *operation,
    search=None,
    context=2,
    all=False,
    mutate=False,
):
    """Return source metadata for the operation normal dispatch would execute."""
    del mutate
    if not operation:
        raise TypeError("source requires an operation")

    from .dispatch import resolution_candidates, resolve_operation
    from .tokens import tokenize

    resolution = resolve_operation(gateway, tokenize(" ".join(map(str, operation))))
    canonical = resolution.candidate
    if not gateway._operation_visible(canonical):
        from .authorization import AuthorizationError

        raise AuthorizationError("Operation is not authorized for source inspection")
    if resolution.arguments:
        raise LookupError(
            "source target includes unresolved arguments: "
            + " ".join(map(str, resolution.arguments))
        )
    descriptor = describe_resolved_source(resolution)
    if all:
        if search is not None:
            raise TypeError("source --all cannot be combined with --search")
        candidates = resolution_candidates(gateway, resolution)
        selected = describe_resolved_source(candidates[0]).result()
        shadowed = [
            describe_resolved_source(candidate).result()
            for candidate in candidates[1:]
        ]
        return {
            "operation": resolution.candidate.replace(".", " "),
            "selected": selected,
            "shadowed": shadowed,
        }
    if search is not None:
        return search_descriptor(descriptor, search, context=context)
    return descriptor.result()


def _source_topics(callable_):
    """Return explicit semantic topics attached by operation ingestion."""
    metadata = getattr(callable_, "__gway_metadata__", {})
    topics = metadata.get("topics", ())
    if isinstance(topics, str):
        topics = (topics,)
    return tuple(
        dict.fromkeys(
            str(topic).strip()
            for topic in topics
            if str(topic).strip()
        )
    )


def _corpus_descriptor(gateway, record):
    """Describe one registered operation without introducing alternate resolution."""
    callable_ = record.callable
    resolution = type(
        "_CorpusResolution",
        (),
        {"callable": callable_, "candidate": record.name},
    )()
    return describe_resolved_source(resolution)


def search_source_corpus(
    gateway,
    query,
    *,
    kind=None,
    topic=(),
    context=0,
    mutate=False,
):
    """Search retrievable sources belonging to registered Gway operations."""
    del mutate
    if context < 0:
        raise ValueError("source search context must be non-negative")

    topics = (topic,) if isinstance(topic, str) else tuple(topic)
    topics = tuple(str(value).strip() for value in topics if str(value).strip())
    wanted_topics = set(topics)
    results = []

    for record in sorted(gateway.ops.records(), key=lambda item: item.name):
        if not gateway._operation_visible(record.name):
            continue
        callable_ = record.callable
        source_kind = getattr(callable_, "__gway_source_kind__", None) or "python"
        normalized_kind = "recipe" if source_kind == "recipe" else "python"
        if kind is not None and normalized_kind != str(kind):
            continue

        operation_topics = set(_source_topics(callable_))
        if wanted_topics and not wanted_topics.issubset(operation_topics):
            continue

        descriptor = _corpus_descriptor(gateway, record)
        searched = search_descriptor(descriptor, query, context=context)
        if not searched["matches"]:
            continue
        results.append(
            {
                "operation": record.name.replace(".", " "),
                "kind": normalized_kind,
                "path": descriptor.path,
                "topics": sorted(operation_topics),
                "matches": searched["matches"],
            }
        )
    return results
