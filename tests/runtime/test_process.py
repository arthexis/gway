from gway.console import process


def test_process_executes_exposed_callable(gateway):
    def echo(value: str):
        return value
    gateway.echo = gateway.wrap("echo_value", echo)
    results, last = process([["echo", "hello"]], gw_instance=gateway)
    assert results == ["hello"]
    assert last == "hello"


def test_process_passes_keyword_arguments(gateway):
    def set_limit(*, limit: int):
        return limit
    gateway.set_limit = gateway.wrap("set_limit", set_limit)
    _, last = process([["set_limit", "--limit", "32"]], gw_instance=gateway)
    assert last == 32


def test_process_can_chain_through_published_subject(gateway):
    def get_charger():
        return "CHG001"
    def inspect_charger(charger):
        return f"inspect:{charger}"
    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)
    results, last = process([["get_charger"], ["inspect_charger"]], gw_instance=gateway)
    assert results == ["CHG001", "inspect:CHG001"]
    assert last == "inspect:CHG001"
