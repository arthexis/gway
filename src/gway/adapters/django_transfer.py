from __future__ import annotations

import argparse
import threading
from collections.abc import Callable
from typing import Any

from gway.project import Project
from gway.transfer import decode_transfer

from .django import DjangoAdapter


def _transfer_converter(converter: Callable[[str], object] | None) -> Callable[[str], object]:
    """Decode one opaque transfer after option parsing but before Django validation."""

    def convert(value: str) -> object:
        restored = decode_transfer(value)
        if converter is None:
            return restored
        text = restored if isinstance(restored, str) else str(restored)
        return converter(text)

    return convert


def _registered_converter(parser: argparse.ArgumentParser, converter: object) -> object:
    """Resolve argparse type names through the owning parser registry."""
    if not isinstance(converter, str):
        return converter
    return parser._registries.get("type", {}).get(converter, converter)


def _wrap_parser_actions(parser: argparse.ArgumentParser) -> None:
    """Wrap value-consuming actions recursively, including child subparsers."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                _wrap_parser_actions(child)
            continue
        if action.nargs == 0:
            continue
        converter = _registered_converter(parser, action.type)
        if isinstance(converter, str):
            continue
        action.type = _transfer_converter(converter)


class TransferDjangoAdapter(DjangoAdapter):
    """Django adapter variant that restores chain values at parser conversion time."""

    def __init__(self, project: Project) -> None:
        super().__init__(project)
        self._transfer_lock = threading.RLock()

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        command = self.describe(path)
        django_command = command.adapter_data
        if django_command is None:
            return super().run(path, argv)

        original_create_parser = django_command.create_parser

        def create_parser(*args: Any, **kwargs: Any):
            parser = original_create_parser(*args, **kwargs)
            _wrap_parser_actions(parser)
            return parser

        with self._transfer_lock:
            django_command.create_parser = create_parser
            try:
                return super().run(path, argv)
            finally:
                django_command.create_parser = original_create_parser


__all__ = ["TransferDjangoAdapter"]
