from gway import Gateway
from gway.console import process


def test_interactive_prompts_only_for_missing_required(monkeypatch):
    runtime = Gateway(interactive=True)
    runtime.context.clear()
    runtime.results.clear()

    def create_charger(serial: str, *, limit: int = 32):
        return serial, limit

    runtime.create_charger = runtime.wrap_callable("create_charger", create_charger)
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "ABC"

    monkeypatch.setattr("builtins.input", fake_input)
    _, last = process([["create_charger"]], gw_instance=runtime)
    assert last == ("ABC", 32)
    assert prompts == ["serial: "]
