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
