from __future__ import annotations

import inspect

from gway.transfer import decode_transfer

from . import AdapterError
from .python import _EXPLICIT_NONE, PythonAdapter, _decode_structured_value, _project_import_path


def _decode_value(value: object) -> object:
    """Restore structured and opaque transferred values after argparse parsing."""
    value = _decode_structured_value(value)
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    return decode_transfer(value)


class TransferPythonAdapter(PythonAdapter):
    """Python adapter variant that restores opaque chain values after CLI parsing."""

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        command = self.describe(path)
        function = command.adapter_data
        if not callable(function):
            raise AdapterError(f"Python command {' '.join(path)} is not callable")

        parser = self._parser_for(command)
        if "--help" in argv or "-h" in argv:
            parser.print_help()
            return None

        namespace = parser.parse_args(argv)
        values = {key: _decode_value(value) for key, value in vars(namespace).items()}
        signature = inspect.signature(function)
        positional: list[object] = []
        keywords: dict[str, object] = {}
        for parameter in signature.parameters.values():
            value = values.get(parameter.name)
            explicit_none = value is _EXPLICIT_NONE
            if explicit_none:
                value = None
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                positional.extend(value or [])
            elif parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional.append(value)
            elif (
                parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
                and parameter.default is inspect.Parameter.empty
            ):
                positional.append(value)
            elif value is not None or explicit_none:
                keywords[parameter.name] = value

        with _project_import_path(self.project):
            return function(*positional, **keywords)


__all__ = ["TransferPythonAdapter"]
