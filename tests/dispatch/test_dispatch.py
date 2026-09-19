import logging

import pytest

from gway.dispatch import dispatch, dispatch_stage, resolve_operation
from gway.operations import Cardinality


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
    gateway.logger.setLevel(logging.INFO)

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
    def get_report():
        return {"items": ["A", "B"]}

    def count_items(items):
        return len(items)

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.count_items = gateway.wrap("count_items", count_items)

    assert dispatch(gateway, "get_report ; count_items") == 2


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


def test_semicolon_preserves_named_results_without_raw_transfer(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)

    assert dispatch(gateway, "get_charger ; inspect_charger") == "inspect:CHG001"



def test_resolve_operation_records_singular_subject_cardinality(gateway):
    def filter_charger():
        return "one"

    wrapped = gateway.wrap("filter_charger", filter_charger)
    resolution = resolve_operation(gateway, ["filter", "charger"])

    func, remaining, name = resolution
    assert func is wrapped
    assert remaining == []
    assert name == "filter charger"
    assert resolution.subject == "charger"
    assert resolution.cardinality is Cardinality.ONE


def test_resolve_operation_accepts_plural_subject_as_many(gateway):
    def filter_charger():
        return "one"

    wrapped = gateway.wrap("filter_charger", filter_charger)
    resolution = resolve_operation(gateway, ["filter", "chargers"])

    func, remaining, name = resolution
    assert func is wrapped
    assert remaining == []
    assert name == "filter chargers"
    assert resolution.subject == "charger"
    assert resolution.cardinality is Cardinality.MANY


@pytest.mark.parametrize(
    ("singular", "plural"),
    [
        ("charger", "chargers"),
        ("category", "categories"),
        ("box", "boxes"),
        ("status", "statuses"),
    ],
)
def test_plural_subject_resolution_uses_shared_inflection(
    gateway,
    singular,
    plural,
):
    def inspect():
        return singular

    wrapped = gateway.wrap(
        f"inspect_{singular}",
        inspect,
        op="inspect",
        sub=singular,
    )

    resolution = resolve_operation(gateway, ["inspect", plural])

    assert resolution.callable is wrapped
    assert resolution.subject == singular
    assert resolution.cardinality is Cardinality.MANY


def test_singular_subject_ending_in_double_s_stays_one(gateway):
    def inspect_glass():
        return "glass"

    wrapped = gateway.wrap("inspect_glass", inspect_glass)
    resolution = resolve_operation(gateway, ["inspect", "glass"])

    assert resolution.callable is wrapped
    assert resolution.subject == "glass"
    assert resolution.cardinality is Cardinality.ONE


def test_one_token_plural_subject_resolves_singular_selector(gateway):
    def select_charger(identity):
        return identity

    wrapped = gateway.wrap(
        "charger",
        select_charger,
        op="charger",
        sub="charger",
    )

    resolution = resolve_operation(gateway, ["chargers", "CHG001"])

    assert resolution.callable is wrapped
    assert [str(token) for token in resolution.arguments] == ["CHG001"]
    assert resolution.subject == "charger"
    assert resolution.cardinality is Cardinality.MANY


def test_exact_plural_subject_wins_over_inferred_singular(gateway):
    def singular():
        return "singular"

    def plural():
        return "plural"

    singular_wrapped = gateway.wrap(
        "inspect_charger",
        singular,
        op="inspect",
        sub="charger",
    )
    plural_wrapped = gateway.wrap(
        "inspect_chargers",
        plural,
        op="inspect",
        sub="chargers",
    )

    resolution = resolve_operation(gateway, ["inspect", "chargers"])

    assert resolution.callable is plural_wrapped
    assert resolution.callable is not singular_wrapped
    assert resolution.subject == "chargers"
    assert resolution.cardinality is Cardinality.ONE
