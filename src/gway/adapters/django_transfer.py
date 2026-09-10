from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from gway.transfer import render_transfer

from .django import DjangoAdapter


def _restore_parsed_value(value: object) -> object:
    """Restore opaque transfer values after Django has finished parsing argv."""
    if isinstance(value, Mapping):
        return {key: _restore_parsed_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_restore_parsed_value(item) for item in value)
    if isinstance(value, list):
        return [_restore_parsed_value(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return type(value)(_restore_parsed_value(item) for item in value)
    return render_transfer(value)


class TransferDjangoAdapter(DjangoAdapter):
    """Django adapter variant that restores opaque chain values after parsing."""

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        command = self.describe(path)
        django_command = command.adapter_data
        if django_command is None:
            return super().run(path, argv)

        original_execute = django_command.execute

        def execute(*args: object, **options: Any) -> object:
            restored_args = tuple(_restore_parsed_value(value) for value in args)
            restored_options = {key: _restore_parsed_value(value) for key, value in options.items()}
            return original_execute(*restored_args, **restored_options)

        django_command.execute = execute
        try:
            return super().run(path, argv)
        finally:
            django_command.execute = original_execute


__all__ = ["TransferDjangoAdapter"]
