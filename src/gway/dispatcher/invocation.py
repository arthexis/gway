from __future__ import annotations

from collections.abc import Mapping

from ..command import Command, Parameter
from .errors import DispatchError, InvocationArgumentError


def _argument_key(value: str) -> str:
    """Normalize a named argument independently from its external spelling."""
    return value.replace("-", "_").casefold()


def _programmatic_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise InvocationArgumentError(f"expected boolean value, got {value!r}")


def _parameter_option(parameter: Parameter) -> str:
    return next(
        (name for name in parameter.options if name.startswith("--")),
        f"--{parameter.name.replace('_', '-')}",
    )


def named_arguments_to_argv(
    command: Command,
    arguments: Mapping[str, str],
) -> list[str]:
    """Translate one named string mapping into adapter-facing command argv."""
    parameters: dict[str, Parameter] = {}
    for parameter in command.parameters:
        key = _argument_key(parameter.name)
        if key in parameters:
            raise DispatchError(
                f"ambiguous parameter metadata for {' '.join(command.path)}: {parameter.name}"
            )
        parameters[key] = parameter

    provided: dict[str, str] = {}
    for name, value in arguments.items():
        if not isinstance(name, str):
            raise InvocationArgumentError("programmatic argument names must be strings")
        if not isinstance(value, str):
            raise InvocationArgumentError(
                f"programmatic argument {name!r} must be a string"
            )
        parameter = parameters.get(_argument_key(name))
        if parameter is None:
            raise InvocationArgumentError(
                f"unknown argument for {' '.join(command.path)}: {name}"
            )
        if parameter.name in provided:
            raise InvocationArgumentError(f"duplicate argument: {name}")
        provided[parameter.name] = value

    argv: list[str] = []
    missing: list[str] = []
    for parameter in command.parameters:
        if parameter.name not in provided:
            if parameter.required:
                missing.append(parameter.name)
            continue

        value = provided[parameter.name]
        if parameter.positional:
            argv.append(value)
            continue

        option = _parameter_option(parameter)
        is_boolean = parameter.annotation is bool or parameter.consumes_value is False
        if not is_boolean:
            argv.extend((option, value))
            continue

        enabled = _programmatic_bool(value)
        if enabled:
            argv.append(option)
            continue

        negative_options = parameter.negative_options or ()
        if negative_options:
            argv.append(negative_options[0])
        elif parameter.default is not False:
            raise InvocationArgumentError(
                f"argument {parameter.name!r} does not support false"
            )

    if missing:
        raise InvocationArgumentError(
            f"missing required arguments: {', '.join(missing)}"
        )
    return argv


__all__ = ["named_arguments_to_argv"]
