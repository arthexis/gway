import asyncio
from contextvars import ContextVar
import logging

from gway.runner import invoke


class Runtime:
    timed_enabled = False
    logger = logging.getLogger("gway-test")


def test_invoke_sync_callable():
    runtime = Runtime()

    def add(left, right):
        return left + right

    assert invoke(runtime, "add", add, args=(2, 3)) == 5


def test_invoke_async_callable():
    runtime = Runtime()

    async def add(left, right):
        await asyncio.sleep(0)
        return left + right

    assert invoke(runtime, "add", add, args=(2, 3)) == 5


def test_invoke_rejects_non_callable():
    runtime = Runtime()

    try:
        invoke(runtime, "value", 3)
    except TypeError as exc:
        assert "not callable" in str(exc)
    else:
        raise AssertionError("invoke() should reject non-callables")


def test_invoke_async_callable_inside_running_event_loop():
    runtime = Runtime()

    async def operation():
        await asyncio.sleep(0)
        return "OK"

    async def host():
        return invoke(runtime, "operation", operation)

    assert asyncio.run(host()) == "OK"


def test_nested_loop_worker_propagates_async_exception():
    runtime = Runtime()

    async def operation():
        await asyncio.sleep(0)
        raise ValueError("async failure")

    async def host():
        return invoke(runtime, "operation", operation)

    try:
        asyncio.run(host())
    except ValueError as exc:
        assert str(exc) == "async failure"
    else:
        raise AssertionError("invoke() should propagate async failures")


def test_nested_loop_worker_preserves_contextvars():
    runtime = Runtime()
    request_id = ContextVar("request_id")
    token = request_id.set("notebook-42")

    async def operation():
        await asyncio.sleep(0)
        return request_id.get()

    async def host():
        return invoke(runtime, "operation", operation)

    try:
        assert asyncio.run(host()) == "notebook-42"
    finally:
        request_id.reset(token)


def test_invoke_rejects_future_bound_to_current_running_loop():
    runtime = Runtime()

    async def host():
        future = asyncio.get_running_loop().create_future()
        future.set_result("already-complete")

        try:
            invoke(runtime, "future", lambda: future)
        except RuntimeError as exc:
            assert "Future or Task" in str(exc)
        else:
            raise AssertionError("invoke() should reject loop-bound futures")

    asyncio.run(host())
