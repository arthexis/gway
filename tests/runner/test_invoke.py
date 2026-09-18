import asyncio
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
