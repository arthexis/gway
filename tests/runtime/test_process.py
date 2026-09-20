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


def test_process_chains_through_explicit_pipeline(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)
    results, last = process(
        [["get_charger", "-", "inspect_charger"]],
        gw_instance=gateway,
    )
    assert results == ["CHG001", "inspect:CHG001"]
    assert last == "inspect:CHG001"


def test_process_pipeline_does_not_require_matching_published_subject(gateway):
    report = object()

    def get_report():
        return report

    def consume_items(items):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)

    results, last = process(
        [["get_report", "-", "consume_items"]],
        gw_instance=gateway,
    )

    assert results[0] is report
    assert last is report


def test_process_newline_can_resolve_published_mapping_semantically(gateway):
    report = {"chargers": 3}

    def get_report():
        return report

    def inspect_report(report):
        assert report is gateway.results["report"]
        return report

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.inspect_report = gateway.wrap("inspect_report", inspect_report)

    results, last = process([["get_report"], ["inspect_report"]], gw_instance=gateway)

    assert results[0] is report
    assert last is report
