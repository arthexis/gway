from gway import Gateway
from gway.binding import bind_arguments


def test_interactive_prompts_only_for_missing_required(monkeypatch):
    runtime = Gateway(interactive=True)
    runtime.context.clear()
    runtime.results.clear()

    def create_charger(serial: str, *, limit: int = 32):
        return serial, limit

    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "ABC"

    monkeypatch.setattr("builtins.input", fake_input)
    bound = bind_arguments(
        create_charger,
        [],
        runtime=runtime,
        interactive=True,
    )

    assert bound.args == ("ABC",)
    assert bound.kwargs == {}
    assert prompts == ["serial: "]
