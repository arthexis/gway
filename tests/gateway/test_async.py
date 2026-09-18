import asyncio


def test_async_callable_runs(gateway):
    async def get_charger():
        await asyncio.sleep(0)
        return "ASYNC"

    assert gateway.wrap("get_charger", get_charger)() == "ASYNC"
    assert gateway.results["charger"] == "ASYNC"
