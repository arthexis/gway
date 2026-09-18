import pytest


def test_chain_runs_head_on_entry_and_returns_scoped_callable(gateway):
    def chargers():
        return ["A", "B"]

    gateway.chargers = gateway.wrap("get_chargers", chargers)

    with gateway.chain("chargers") as __:
        assert __.head == ["A", "B"]
        assert __.last is __.head
        assert __.history == [__.head]


def test_chain_pipes_previous_result_into_next_command(gateway):
    def chargers():
        return ["A", "B"]

    def count_chargers(chargers):
        return len(chargers)

    gateway.chargers = gateway.wrap("get_chargers", chargers)
    gateway.count = gateway.wrap("count_chargers", count_chargers)

    with gateway.chain("chargers") as __:
        assert __("count") == 2
        assert __.last == 2
        assert __.history == [["A", "B"], 2]


def test_chain_binds_inline_arguments_after_pipeline_value(gateway):
    def chargers():
        return ["A", "B", "C"]

    def filter_chargers(chargers, prefix: str):
        return [charger for charger in chargers if charger.startswith(prefix)]

    gateway.chargers = gateway.wrap("get_chargers", chargers)
    gateway.filter = gateway.wrap("filter_chargers", filter_chargers)

    with gateway.chain("chargers") as __:
        assert __("filter A") == ["A"]


def test_chain_accepts_native_keyword_arguments(gateway):
    def chargers():
        return ["A", "B"]

    def report_chargers(chargers, *, title):
        return title, chargers

    gateway.chargers = gateway.wrap("get_chargers", chargers)
    gateway.report = gateway.wrap("report_chargers", report_chargers)

    with gateway.chain("chargers") as __:
        assert __("report", title="Fleet") == ("Fleet", ["A", "B"])


def test_chain_requires_with_block(gateway):
    def chargers():
        return ["A"]

    gateway.chargers = gateway.wrap("get_chargers", chargers)
    chain = gateway.chain("chargers")

    with pytest.raises(RuntimeError, match="active with block"):
        chain("count")


def test_chain_call_accepts_one_stage_at_a_time(gateway):
    def chargers():
        return ["A"]

    def count_chargers(chargers):
        return len(chargers)

    gateway.chargers = gateway.wrap("get_chargers", chargers)
    gateway.count = gateway.wrap("count_chargers", count_chargers)

    with gateway.chain("chargers") as __:
        with pytest.raises(ValueError, match="one command stage"):
            __("count - count")
