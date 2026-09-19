from gway.console import process


def _install_pipeline(gateway, value):
    def get_report():
        return value

    def consume_items(items):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)


def test_dash_and_manual_chain_transfer_raw_pipeline_values(gateway):
    marker = object()
    _install_pipeline(gateway, marker)

    assert gateway("get_report - consume_items") is marker

    with gateway.chain("get_report") as __:
        assert __("consume_items") is marker


def test_recipe_newline_does_not_transfer_raw_pipeline_values(gateway):
    marker = object()

    def get_report():
        return marker

    def consume_items(items="default"):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)

    _, recipe_last = process(
        [["get_report"], ["consume_items"]],
        gw_instance=gateway,
    )

    assert recipe_last == "default"


def test_process_preserves_dash_pipeline_inside_one_statement(gateway):
    marker = object()
    _install_pipeline(gateway, marker)

    results, last = process(
        [["get_report", "-", "consume_items"]],
        gw_instance=gateway,
    )

    assert results == [marker, marker]
    assert last is marker


def test_recipe_newline_preserves_named_semantic_results(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)

    results, last = process(
        [["get_charger"], ["inspect_charger"]],
        gw_instance=gateway,
    )

    assert results == ["CHG001", "inspect:CHG001"]
    assert last == "inspect:CHG001"


def test_dash_adds_raw_positional_transfer_without_losing_named_context(gateway):
    raw = object()

    def get_report():
        return {"site": "MTY"}

    def produce_raw():
        return raw

    def consume(value, site):
        return value, site

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.produce_raw = gateway.wrap("produce_raw", produce_raw)
    gateway.consume = gateway.wrap("consume_value", consume)

    process([["get_report"]], gw_instance=gateway)
    result = gateway("produce_raw - consume [site]")

    assert result == (raw, "MTY")


def test_named_context_fills_positional_parameter_without_dash(gateway):
    gateway.context["chargers"] = ["context"]

    def inspect_report(chargers):
        return chargers

    gateway.inspect_report = gateway.wrap("inspect_report", inspect_report)

    assert gateway("inspect_report") == ["context"]


def test_dash_uses_position_before_name_matching(gateway):
    gateway.context["chargers"] = ["context"]

    def get_report():
        return ["pipeline"]

    def inspect_report(chargers):
        return chargers

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.inspect_report = gateway.wrap("inspect_report", inspect_report)

    assert gateway("get_report - inspect_report") == ["pipeline"]
