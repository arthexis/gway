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
