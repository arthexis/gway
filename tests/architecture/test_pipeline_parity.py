from gway.console import process


def _install_pipeline(gateway, value):
    def get_report():
        return value

    def consume_items(items):
        return items

    gateway.get_report = gateway.wrap("get_report", get_report)
    gateway.consume_items = gateway.wrap("consume_items", consume_items)


def test_command_recipe_and_manual_chain_share_pipeline_semantics(gateway):
    marker = object()
    _install_pipeline(gateway, marker)

    assert gateway("get_report - consume_items") is marker

    _, recipe_last = process(
        [["get_report"], ["consume_items"]],
        gw_instance=gateway,
    )
    assert recipe_last is marker

    with gateway.chain("get_report") as __:
        assert __("consume_items") is marker


def test_process_chunks_inline_stage_separators(gateway):
    marker = object()
    _install_pipeline(gateway, marker)

    results, last = process(
        [["get_report", "-", "consume_items"]],
        gw_instance=gateway,
    )

    assert results == [marker, marker]
    assert last is marker
