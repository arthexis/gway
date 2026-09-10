from __future__ import annotations

import argparse

from gway.adapters.django_transfer import _wrap_parser_actions
from gway.transfer import encode_transfer, transfer_scope


def test_wrap_parser_actions_recurses_into_subparsers() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    child = subparsers.add_parser("child")
    child.add_argument("value", type=int)
    _wrap_parser_actions(parser)

    with transfer_scope():
        token = encode_transfer("42")
        namespace = parser.parse_args(["child", token])

    assert namespace.value == 42


def test_wrap_parser_actions_preserves_registered_type_names() -> None:
    parser = argparse.ArgumentParser()
    parser.register("type", "hex", lambda value: int(value, 16))
    parser.add_argument("value", type="hex")
    _wrap_parser_actions(parser)

    with transfer_scope():
        token = encode_transfer("2a")
        namespace = parser.parse_args([token])

    assert namespace.value == 42


def test_wrap_parser_actions_keeps_registered_type_for_plain_cli_value() -> None:
    parser = argparse.ArgumentParser()
    parser.register("type", "hex", lambda value: int(value, 16))
    parser.add_argument("value", type="hex")
    _wrap_parser_actions(parser)

    namespace = parser.parse_args(["2a"])

    assert namespace.value == 42
