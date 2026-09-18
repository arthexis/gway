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


def test_same_thread_gateways_share_state():
    first = Gateway()
    first.context.clear()
    first.results.clear()
    first.context["shared"] = "yes"
    second = Gateway()
    assert second.context["shared"] == "yes"


def test_new_thread_gets_isolated_state():
    gateway = Gateway()
    gateway.context.clear()
    gateway.context["main_only"] = True
    observed = {}

    def worker():
        other = Gateway()
        observed["has_main"] = "main_only" in other.context
        other.context["worker_only"] = True

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert observed["has_main"] is False
    assert "worker_only" not in gateway.context
