def test_result_precedes_context_and_environment(gateway, monkeypatch):
    monkeypatch.setenv("CHARGER", "environment")
    gateway.context["charger"] = "context"
    gateway.results.insert("charger", "result")
    assert gateway.resolve("[charger]") == "result"


def test_context_precedes_environment(gateway, monkeypatch):
    monkeypatch.setenv("SITE", "environment")
    gateway.context["site"] = "context"
    assert gateway.resolve("[site]") == "context"
