import pytest


def test_quoted_sigil_is_exact_lookup_not_literal(gateway):
    gateway.context["status code"] = 200
    assert gateway.resolve('["status code"]') == 200
    with pytest.raises(KeyError):
        gateway.resolve('["missing key"]')


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


def test_resolve_text_preserves_double_bracket_literals(gateway):
    gateway.context["port"] = 80

    assert gateway.resolve("listen [[::]]:[port];") == "listen [::]:80;"


def test_double_bracket_literal_does_not_resolve_inner_name(gateway):
    gateway.context["site"] = "Monterrey"

    assert gateway.resolve("[[site]] [site]") == "[site] Monterrey"


def test_double_bracket_literal_needs_no_lookup(gateway):
    assert gateway.resolve("IPv6 [[::1]]") == "IPv6 [::1]"
