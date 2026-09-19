import logging

import pytest

from gway.dispatch import dispatch, dispatch_stage, resolve_operation


def test_resolve_operation_prefers_registered_ops(gateway):
    def ping():
        return "pong"

    wrapped = gateway.wrap("ping", ping)
    func, remaining, name = resolve_operation(gateway, ["ping"])

    assert func is wrapped
    assert remaining == []
    assert name == "ping"


def test_dispatch_executes_multiple_stages(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)

    assert dispatch(gateway, "get_charger - inspect_charger") == "inspect:CHG001"


def test_dispatch_multistage_uses_raw_pipeline_not_subject_lookup(gateway):
    report = object()

    def get_report():
        return report

    def consume_items(items):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)

    assert dispatch(gateway, "get_report - consume_items") is report


def test_dispatch_stage_accepts_pipeline_before_inline_arguments(gateway):
    def filter_chargers(chargers, prefix: str):
        return [charger for charger in chargers if charger.startswith(prefix)]

    gateway.filter = gateway.wrap("filter_chargers", filter_chargers)

    result = dispatch_stage(
        gateway,
        ["filter", "A"],
        pipeline=["A", "B"],
    )

    assert result == ["A"]


def test_native_arguments_still_reject_inline_tokens(gateway):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)

    with pytest.raises(TypeError, match="without inline arguments"):
        dispatch(gateway, "echo inline", "native")


def test_dispatch_does_not_duplicate_runner_timing(gateway, caplog):
    def ping():
        return "pong"

    gateway.ping = gateway.wrap("ping", ping)
    gateway.timed_enabled = True

    with caplog.at_level(logging.INFO):
        assert dispatch(gateway, "ping") == "pong"

    timed = [record for record in caplog.records if "[timed]" in record.getMessage()]
    assert len(timed) == 1


def test_process_style_stage_sequence_matches_inline_dispatch(gateway):
    from gway.dispatch import dispatch_sequence

    def produce_value():
        return "value"

    def consume_value(value):
        return f"seen:{value}"

    gateway.produce_value = gateway.wrap("produce_value", produce_value)
    gateway.consume_value = gateway.wrap("consume_value", consume_value)

    results, last = dispatch_sequence(
        gateway,
        [["produce_value"], ["consume_value"]],
    )

    assert results == ["value", "seen:value"]
    assert last == "seen:value"
    assert dispatch(gateway, "produce_value - consume_value") == last


def test_semicolon_starts_new_statement_without_raw_pipeline(gateway):
    marker = object()

    def get_report():
        return marker

    def consume_items(items="default"):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)

    assert dispatch(gateway, "get_report ; consume_items") == "default"


def test_semicolon_statement_still_sees_published_semantic_context(gateway):
    def get_items():
        return {"items": ["A", "B"]}

    def count_items(items):
        return len(items)

    gateway.get_items = gateway.wrap("get_items", get_items)
    gateway.count_items = gateway.wrap("count_items", count_items)

    assert dispatch(gateway, "get_items ; count_items") == 2


def test_greedy_final_string_consumes_dash_and_double_dash_until_statement_end(gateway):
    def select(predicate: str):
        return predicate

    gateway.select = gateway.wrap("select", select)

    assert (
        dispatch(gateway, "select * from users where Some - Dept -- literal ;")
        == "* from users where Some - Dept -- literal"
    )


def test_options_can_precede_greedy_final_string(gateway):
    def select(predicate: str, *, limit: int = 0):
        return predicate, limit

    gateway.select = gateway.wrap("select", select)

    assert dispatch(
        gateway,
        "select --limit 5 * from users where Some - Dept ;",
    ) == ("* from users where Some - Dept", 5)
