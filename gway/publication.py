"""Result publication for GWAY runtimes."""

from collections.abc import Mapping


SKIP_PUBLICATION = object()


def publish(runtime, subject, result):
    """Publish a completed result unless the operation is transparently skipped."""
    if result is SKIP_PUBLICATION:
        return runtime.results.last

    runtime.results.insert(subject, result)

    if isinstance(result, Mapping):
        runtime.context.update(result)

    return result
