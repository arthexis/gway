"""Result publication for GWAY runtimes."""

from collections.abc import Mapping


def publish(runtime, subject, result):
    """Publish a completed operation result to history and semantic state."""
    runtime.results.insert(subject, result)

    if subject and isinstance(result, Mapping):
        runtime.context.update(result)

    return result
