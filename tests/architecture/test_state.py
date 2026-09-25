import asyncio
import threading

from gway import Gateway
from gway.structs import Results


def test_results_preserve_scalar_under_subject():
    results = Results()
    results.clear()

    results.insert("charger", "CHG001")
    assert results["charger"] == "CHG001"


def test_results_preserve_mapping_under_subject():
    results = Results()
    results.clear()
    value = {"serial": "CHG001"}

    results.insert("charger", value)
    assert results["charger"] is value
    assert "serial" not in results


def test_results_preserve_arbitrary_object_identity():
    results = Results()
    results.clear()
    value = object()

    results.insert("report", value)
    assert results["report"] is value


def test_results_support_python_style_history_indexing():
    results = Results()
    results.clear()

    results.insert("first", "A")
    results.insert("second", "B")

    assert results[-1] == "B"
    assert results[-2] == "A"
    assert results[0] == "A"


def test_results_last_tracks_none_and_subjectless_values():
    results = Results()
    results.clear()

    results.insert("charger", "CHG001")
    results.insert(None, None)

    assert results.last is None
    assert results[-1] is None
    assert results["charger"] == "CHG001"


def test_results_clear_resets_semantic_and_historical_state():
    results = Results()
    results.clear()
    results.insert("charger", "CHG001")

    results.clear()

    assert results.last is None
    assert len(results.history) == 0
    assert "charger" not in results


def test_gateway_instances_own_independent_root_state():
    first = Gateway()
    first.context.clear()
    first.results.clear()
    first.context["shared"] = "yes"

    second = Gateway()
    second.context.clear()
    second.results.clear()

    assert "shared" not in second.context


def test_request_scopes_isolate_logical_requests_on_same_event_loop_thread():
    gateway = Gateway()
    gateway.context.clear()

    async def probe(value):
        with gateway.request_scope():
            gateway.context["request"] = value
            gateway.results.insert("request", value)
            await asyncio.sleep(0)
            return gateway.context["request"], gateway.results["request"]

    async def scenario():
        return await asyncio.gather(probe("alpha"), probe("beta"))

    assert asyncio.run(scenario()) == [
        ("alpha", "alpha"),
        ("beta", "beta"),
    ]
    assert "request" not in gateway.context
    assert "request" not in gateway.results


def test_request_scopes_isolate_requests_on_different_threads():
    gateway = Gateway()
    gateway.context.clear()
    barrier = threading.Barrier(2)
    observed = {}

    def worker(name):
        with gateway.request_scope():
            gateway.context["request"] = name
            gateway.results.insert("request", name)
            barrier.wait()
            observed[name] = (
                gateway.context["request"],
                gateway.results["request"],
            )

    threads = [
        threading.Thread(target=worker, args=("alpha",)),
        threading.Thread(target=worker, args=("beta",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert observed == {
        "alpha": ("alpha", "alpha"),
        "beta": ("beta", "beta"),
    }
    assert "request" not in gateway.context
    assert "request" not in gateway.results
