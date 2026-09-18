import pytest

from gway.console import chunk, parse_recipe_context, process


def test_process_executes_exposed_callable(gateway):
    def echo(value: str):
        return value

    gateway.echo = gateway.wrap_callable("echo_value", echo)
    results, last = process([["echo", "hello"]], gw_instance=gateway)
    assert results == ["hello"]
    assert last == "hello"


def test_process_passes_keyword_arguments(gateway):
    def set_limit(*, limit: int):
        return limit

    gateway.set_limit = gateway.wrap_callable("set_limit", set_limit)
    _, last = process(
        [["set_limit", "--limit", "32"]],
        gw_instance=gateway,
    )
    assert last == 32


def test_process_can_chain_through_published_subject(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap_callable("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap_callable("inspect_charger", inspect_charger)

    results, last = process(
        [["get_charger"], ["inspect_charger"]],
        gw_instance=gateway,
    )
    assert results == ["CHG001", "inspect:CHG001"]
    assert last == "inspect:CHG001"


def test_interactive_prompts_only_for_missing_required(monkeypatch):
    from gway import Gateway

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


def test_unknown_keyword_fails_cleanly(gateway):
    def echo(value: str):
        return value

    gateway.echo = gateway.wrap_callable("echo_value", echo)
    with pytest.raises(TypeError, match="Unknown argument"):
        process([["echo", "--missing", "x"]], gw_instance=gateway)


def test_parse_recipe_context():
    assert parse_recipe_context(["--site", "MTY", "--dry-run"]) == {
        "site": "MTY",
        "dry_run": True,
    }


def test_chunk_splits_only_standalone_stage_separators():
    assert chunk(["one", "--value", "a-b", "-", "two"]) == [
        ["one", "--value", "a-b"],
        ["two"],
    ]
