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


def test_chain_tuple_result_prefixes_explicit_native_positionals(gateway):
    def pair():
        return ("A", "B")

    def combine(first, second, third):
        return first, second, third

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)

    with gateway.chain("pair") as __:
        assert __("combine", "C") == ("A", "B", "C")


def test_dash_tuple_result_prefixes_inline_positionals(gateway):
    def pair():
        return ("A", "B")

    def combine(first, second, third):
        return first, second, third

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("pair - combine C") == ("A", "B", "C")


def test_chain_prefix_then_explicit_then_named_completion(gateway):
    gateway.context["fourth"] = "D"

    def pair():
        return ("A", "B")

    def combine(first, second, third, fourth):
        return first, second, third, fourth

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)

    with gateway.chain("pair") as __:
        assert __("combine", "C") == ("A", "B", "C", "D")


def test_chain_numeric_sigils_reorder_original_tuple_positions(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third):
        return first, second, third

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("triple - combine [2] [0] [1]") == ("C", "A", "B")


def test_chain_numeric_sigils_remove_selected_values_from_default_prefix(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third):
        return first, second, third

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("triple - combine [2] [0]") == ("B", "C", "A")


def test_chain_star_places_remaining_tuple_values_at_marker(gateway):
    def pair():
        return ("A", "B")

    def combine(first, second, third):
        return first, second, third

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("pair - combine C [*]") == ("C", "A", "B")


def test_chain_numeric_then_star_consumes_remaining_values(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third):
        return first, second, third

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("triple - combine [2] [*]") == ("C", "A", "B")


def test_chain_repeated_numeric_selector_duplicates_snapshot_value(gateway):
    def pair():
        return ("A", "B")

    def combine(first, second, third):
        return first, second, third

    gateway.pair = gateway.wrap("get_pair", pair)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("pair - combine [1] [1]") == ("A", "B", "B")


def test_repeated_numeric_selector_consumes_source_slot_only_once(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third, fourth, fifth):
        return first, second, third, fourth, fifth

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("triple - combine [1] [1] [1]") == ("A", "C", "B", "B", "B")


def test_numeric_selector_after_star_uses_same_snapshot(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third):
        return first, second, third

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    assert gateway("triple - combine [*] [1]") == ("A", "C", "B")


def test_manual_chain_supports_numeric_and_star_selectors(gateway):
    def triple():
        return ("A", "B", "C")

    def combine(first, second, third, fourth):
        return first, second, third, fourth

    gateway.triple = gateway.wrap("get_triple", triple)
    gateway.combine = gateway.wrap("combine_values", combine)

    with gateway.chain("triple") as __:
        assert __("combine X [2] [*]") == ("X", "C", "A", "B")
