"""Callable invocation for GWAY runtimes."""

import asyncio
import inspect
import time


def _run_awaitable(awaitable):
    """Run an awaitable synchronously at the GWAY invocation boundary."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


def invoke(runtime, name, func, args=(), kwargs=None):
    """Invoke a callable, awaiting its result when needed and applying timing policy."""
    if not callable(func):
        raise TypeError(f"{name!r} is not callable")

    kwargs = {} if kwargs is None else kwargs
    start = time.perf_counter() if getattr(runtime, "timed_enabled", False) else None

    try:
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            result = _run_awaitable(result)
        return result
    finally:
        if start is not None and hasattr(runtime, "logger"):
            runtime.logger.info(
                "[timed] %s took %.3fs",
                name,
                time.perf_counter() - start,
            )
