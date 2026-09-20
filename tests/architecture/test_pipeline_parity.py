from gway.console import process


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
