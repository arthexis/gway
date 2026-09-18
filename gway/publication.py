"""Result publication for GWAY runtimes."""


def publish(runtime, subject, result):
    """Publish a result using the runtime's current semantic conventions."""
    if not subject or result is None:
        return result

    runtime.results.insert(subject, result)
    if isinstance(result, dict):
        runtime.context.update(result)
    return result
