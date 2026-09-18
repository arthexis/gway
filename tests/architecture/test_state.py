import threading

from gway import Gateway


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
