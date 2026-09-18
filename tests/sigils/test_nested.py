import pytest

from gway.console import Token, process


def test_nested_sigil_selects_mapping_key(gateway):
    gateway.context["field"] = "serial"
    gateway.context["charger"] = {"serial": "ABC", "status": "online"}
    assert gateway.resolve("[charger [field]]") == "ABC"


def test_nested_sigil_selects_sequence_index(gateway):
    gateway.context["index"] = 1
    gateway.context["chargers"] = ["A", "B", "C"]
    assert gateway.resolve("[chargers [index]]") == "B"


def test_nested_sigil_continues_path_after_dynamic_selector(gateway):
    gateway.context["index"] = 1
    gateway.context["response"] = {
        "payload": {"chargers": [{"serial": "A"}, {"serial": "B"}]}
    }
    assert gateway.resolve("[response payload chargers [index] serial]") == "B"


def test_nested_sigil_can_resolve_non_string_mapping_key(gateway):
    gateway.context["key"] = 3
    gateway.context["values"] = {3: "three"}
    assert gateway.resolve("[values [key]]") == "three"


def test_unresolved_inner_sigil_fails(gateway):
    gateway.context["chargers"] = ["A", "B"]
    with pytest.raises(KeyError):
        gateway.resolve("[chargers [missing_index]]")


def test_nested_sigil_in_double_quoted_token_can_resolve(gateway):
    gateway.context["field"] = "serial"
    gateway.context["charger"] = {"serial": "ABC"}

    def echo(value: str):
        return value

    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process(
        [[Token("echo"), Token("[charger [field]]", "double")]],
        gw_instance=gateway,
    )
    assert last == "ABC"


def test_nested_sigil_in_single_quoted_token_is_literal(gateway):
    gateway.context["field"] = "serial"
    gateway.context["charger"] = {"serial": "ABC"}

    def echo(value: str):
        return value

    gateway.echo = gateway.wrap_callable("echo_value", echo)
    _, last = process(
        [[Token("echo"), Token("[charger [field]]", "single")]],
        gw_instance=gateway,
    )
    assert last == "[charger [field]]"
