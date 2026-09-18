"""Result publication for GWAY runtimes."""


def publish(runtime, subject, result):
    """Publish a completed operation result to history and semantic state."""
    runtime.results.insert(subject, result)

    if subject and isinstance(result, dict):
        runtime.context.update(result)

    return result
