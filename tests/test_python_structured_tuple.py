from __future__ import annotations

from gway.adapters.python import _converter, _decode_structured_value
from gway.expression import STRUCTURED_TUPLE_PREFIX


def test_tuple_annotation_is_supported_for_structured_values() -> None:
    converter, choices = _converter(tuple[str, ...])
    assert converter is str
    assert choices is None


def test_structured_tuple_marker_decodes_to_one_tuple_value() -> None:
    value = _decode_structured_value(f"{STRUCTURED_TUPLE_PREFIX}wlan0,eth0")
    assert value == ("wlan0", "eth0")


def test_empty_structured_tuple_decodes_to_empty_tuple() -> None:
    assert _decode_structured_value(STRUCTURED_TUPLE_PREFIX) == ()
