"""Result publication for GWAY runtimes."""

from collections.abc import Mapping


SKIP_PUBLICATION = object()


class ResultOnlyMapping(dict):
    """Mapping result whose members must not be promoted into semantic context."""

    __gway_publish_context__ = False


def publish(runtime, subject, result):
    """Publish a completed result unless the operation is transparently skipped."""
    if result is SKIP_PUBLICATION:
        return runtime.results.last

    runtime.results.insert(subject, result)

    if isinstance(result, Mapping) and getattr(
        result, "__gway_publish_context__", True
    ):
        runtime.context.update(result)

    return result
