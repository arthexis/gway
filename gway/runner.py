"""Callable execution support for GWAY runtimes."""

import asyncio
import contextvars
import inspect
import threading
import time


async def _await_result(awaitable):
    """Await one value inside the event loop that owns this execution."""
    return await awaitable


def _run_awaitable_in_thread(awaitable):
    """Await one coroutine on a worker thread while preserving context vars."""
    context = contextvars.copy_context()
    outcome = {}

    def run():
        try:
            outcome["result"] = context.run(
                asyncio.run,
                _await_result(awaitable),
            )
        except BaseException as exc:
            outcome["exception"] = exc

    worker = threading.Thread(target=run, name="gway-awaitable", daemon=True)
    worker.start()
    worker.join()

    if "exception" in outcome:
        raise outcome["exception"]
    return outcome["result"]


def _run_awaitable(awaitable):
    """Run an awaitable synchronously at the GWAY execution boundary."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_result(awaitable))

    if isinstance(awaitable, asyncio.Future):
        raise RuntimeError(
            "GWAY cannot synchronously wait for a Future or Task bound to "
            "the currently running event loop"
        )

    return _run_awaitable_in_thread(awaitable)


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
