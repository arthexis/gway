from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..command import Command, Parameter


def _option_names(parameter: Parameter) -> tuple[str, ...]:
    if parameter.options:
        return parameter.options
    return (f"--{parameter.name.replace('_', '-')}",)


def _negative_option_names(parameter: Parameter) -> tuple[str, ...]:
    if parameter.negative_options is not None:
        return parameter.negative_options
    if parameter.annotation is bool:
        return tuple(
            f"--no-{option[2:]}"
            for option in _option_names(parameter)
            if option.startswith("--") and not option.startswith("--no-")
        )
    return ()


def _option_name(parameter: Parameter) -> str:
    options = _option_names(parameter)
    long_options = [option for option in options if option.startswith("--")]
    return long_options[0] if long_options else options[0]


def _option_consumes_value(parameter: Parameter) -> bool:
    if parameter.consumes_value is not None:
        return parameter.consumes_value
    return parameter.annotation is not bool


def _attached_short_option(token: str, option: str, parameter: Parameter) -> bool:
    return (
        option.startswith("-")
        and not option.startswith("--")
        and len(option) == 2
        and token.startswith(option)
        and token != option
        and _option_consumes_value(parameter)
    )


def _abbreviated_long_option(token: str, option: str) -> bool:
    option_name = token.partition("=")[0]
    return (
        option.startswith("--")
        and option_name.startswith("--")
        and option_name != "--"
        and option.startswith(option_name)
    )


def _option_present(argv: Sequence[str], parameter: Parameter) -> bool:
    for option in _option_names(parameter):
        for token in argv:
            if token == option or token.startswith(f"{option}="):
                return True
            if _abbreviated_long_option(token, option):
                return True
            if _attached_short_option(token, option, parameter):
                return True
    for option in _negative_option_names(parameter):
        for token in argv:
            if token == option or _abbreviated_long_option(token, option):
                return True
    return False


def _match_option(
    token: str, option_parameters: Mapping[str, Parameter]
) -> tuple[Parameter | None, bool]:
    option_name, separator, _ = token.partition("=")
    parameter = option_parameters.get(option_name)
    if parameter is not None:
        return parameter, bool(separator)
    if option_name.startswith("--") and option_name != "--":
        matches = [
            candidate
            for option, candidate in option_parameters.items()
            if option.startswith("--") and option.startswith(option_name)
        ]
        if matches and all(candidate is matches[0] for candidate in matches):
            return matches[0], bool(separator)
    for option, candidate in option_parameters.items():
        if _attached_short_option(token, option, candidate):
            return candidate, True
    return None, False


def _match_negative_option(
    token: str, option_parameters: Mapping[str, Parameter]
) -> Parameter | None:
    option_name, _, _ = token.partition("=")
    parameter = option_parameters.get(option_name)
    if parameter is not None:
        return parameter
    if option_name.startswith("--") and option_name != "--":
        matches = [
            candidate
            for option, candidate in option_parameters.items()
            if option.startswith("--") and option.startswith(option_name)
        ]
        if matches and all(candidate is matches[0] for candidate in matches):
            return matches[0]
    return None


def _option_value_count(
    parameter: Parameter,
    argv: Sequence[str],
    start: int,
    option_parameters: Mapping[str, Parameter],
    negative_option_parameters: Mapping[str, Parameter] | None = None,
) -> int:
    negative_option_parameters = negative_option_parameters or {}
    arity = parameter.option_arity
    if isinstance(arity, int):
        return max(0, min(arity, len(argv) - start))
    if arity in {"*", "+"}:
        count = 0
        while start + count < len(argv):
            token = argv[start + count]
            matched, _ = _match_option(token, option_parameters)
            negative = _match_negative_option(token, negative_option_parameters)
            if token == "--" or matched is not None or negative is not None:
                break
            count += 1
        return count
    if arity == "?":
        if start >= len(argv):
            return 0
        token = argv[start]
        matched, _ = _match_option(token, option_parameters)
        negative = _match_negative_option(token, negative_option_parameters)
        return 0 if token == "--" or matched is not None or negative is not None else 1
    return 1 if _option_consumes_value(parameter) and start < len(argv) else 0


def _option_parameters(command: Command) -> dict[str, Parameter]:
    result: dict[str, Parameter] = {}
    for parameter in command.parameters:
        if parameter.positional:
            continue
        for option in _option_names(parameter):
            result[option] = parameter
        if parameter.annotation is bool:
            for option in _negative_option_names(parameter):
                result[option] = parameter
    return result


def _negative_option_parameters(command: Command) -> dict[str, Parameter]:
    result: dict[str, Parameter] = {}
    for parameter in command.parameters:
        if parameter.positional or parameter.annotation is bool:
            continue
        for option in _negative_option_names(parameter):
            result[option] = parameter
    return result
