from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..command import Command, Parameter
from ..expression import STRUCTURED_ARG_PREFIX, STRUCTURED_KWARG_PREFIX
from ..transfer import encode_transfer
from .errors import DispatchError
from .options import (
    _match_negative_option,
    _match_option,
    _negative_option_names,
    _negative_option_parameters,
    _option_name,
    _option_parameters,
    _option_value_count,
)


def _structured_keyword_counts(argv: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    literal = False
    for token in argv:
        if not literal and token == "--":
            literal = True
            continue
        if literal or not token.startswith(STRUCTURED_KWARG_PREFIX):
            continue
        payload = token[len(STRUCTURED_KWARG_PREFIX) :]
        name, separator, _ = payload.partition("=")
        if separator:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _provided_positional_count(command: Command, argv: Sequence[str]) -> int:
    option_parameters = _option_parameters(command)
    negative_option_parameters = _negative_option_parameters(command)
    count = 0
    index = 0
    literal = False
    while index < len(argv):
        token = argv[index]
        if not literal and token == "--":
            literal = True
            index += 1
            continue
        if not literal and token.startswith(STRUCTURED_KWARG_PREFIX):
            index += 1
            continue
        if not literal and token.startswith(STRUCTURED_ARG_PREFIX):
            count += 1
            index += 1
            continue
        if not literal:
            negative = _match_negative_option(token, negative_option_parameters)
            if negative is not None:
                index += 1
                continue
            parameter, attached = _match_option(token, option_parameters)
            if parameter is not None:
                index += 1
                if not attached:
                    index += _option_value_count(
                        parameter, argv, index, option_parameters, negative_option_parameters
                    )
                continue
        count += 1
        index += 1
    return count


def _trailing_variadic_option(command: Command, argv: Sequence[str]) -> bool:
    option_parameters = _option_parameters(command)
    negative_option_parameters = _negative_option_parameters(command)
    active = False
    index = 0
    literal = False
    while index < len(argv):
        token = argv[index]
        if not literal and token == "--":
            literal = True
            active = False
            index += 1
            continue
        if literal:
            active = False
            index += 1
            continue
        negative = _match_negative_option(token, negative_option_parameters)
        if negative is not None:
            active = False
            index += 1
            continue
        parameter, attached = _match_option(token, option_parameters)
        if parameter is not None:
            active = parameter.option_arity in {"*", "+"}
            index += 1
            if not attached and not active:
                index += _option_value_count(
                    parameter, argv, index, option_parameters, negative_option_parameters
                )
            continue
        index += 1
    return active


def _required_positional_count(parameter: Parameter) -> int:
    arity = parameter.option_arity
    if isinstance(arity, int):
        return max(1, arity)
    return 1


def _structured_value_tokens(parameter: Parameter, value: str) -> list[str]:
    if parameter.positional:
        return [value]
    option = _option_name(parameter)
    if parameter.annotation is bool:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return [option]
        if normalized in {"0", "false", "no", "off"}:
            negative_options = _negative_option_names(parameter)
            if negative_options:
                return [negative_options[0]]
            return [option, "false"]
    return [option, value]


def _context_value_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float, Path)):
        return str(value)
    return encode_transfer(value)


def _provided_named_parameters(command: Command, argv: Sequence[str]) -> set[str]:
    """Return named parameters explicitly supplied by the caller."""
    option_parameters = _option_parameters(command)
    negative_option_parameters = _negative_option_parameters(command)
    provided = set(_structured_keyword_counts(argv))
    index = 0
    literal = False
    while index < len(argv):
        token = argv[index]
        if not literal and token == "--":
            literal = True
            index += 1
            continue
        if literal:
            index += 1
            continue
        negative = _match_negative_option(token, negative_option_parameters)
        if negative is not None:
            provided.add(negative.name)
            index += 1
            continue
        parameter, attached = _match_option(token, option_parameters)
        if parameter is not None:
            provided.add(parameter.name)
            index += 1
            if not attached:
                index += _option_value_count(
                    parameter, argv, index, option_parameters, negative_option_parameters
                )
            continue
        index += 1
    return provided


def _fill_context_options(
    command: Command,
    argv: Sequence[str],
    context: Mapping[str, object],
) -> tuple[list[str], dict[str, object]]:
    """Fill omitted named options from context without touching positionals."""
    result = list(argv)
    provided = _provided_named_parameters(command, argv)
    filled: dict[str, object] = {}
    for parameter in command.parameters:
        if parameter.positional or parameter.name in provided or parameter.name not in context:
            continue
        value = context[parameter.name]
        result.extend(_structured_value_tokens(parameter, _context_value_text(value)))
        filled[parameter.name] = value
    return result, filled


def _decode_structured_argv(command: Command, argv: Sequence[str]) -> list[str]:
    positional: list[str] = []
    keywords: dict[str, list[str]] = {}
    ordinary: list[str] = []
    literal = False
    for token in argv:
        if not literal and token == "--":
            literal = True
            ordinary.append(token)
            continue
        if not literal and token.startswith(STRUCTURED_ARG_PREFIX):
            positional.append(token[len(STRUCTURED_ARG_PREFIX) :])
            continue
        if not literal and token.startswith(STRUCTURED_KWARG_PREFIX):
            payload = token[len(STRUCTURED_KWARG_PREFIX) :]
            name, separator, value = payload.partition("=")
            if not separator:
                raise DispatchError(f"invalid structured keyword argument: {payload!r}")
            keywords.setdefault(name, []).append(value)
            continue
        ordinary.append(token)
    if not positional and not keywords:
        return ordinary
    result = list(ordinary)
    values = iter(positional)
    pending = next(values, None)
    known_names = {parameter.name for parameter in command.parameters}
    unknown = set(keywords).difference(known_names)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise DispatchError(f"unknown structured keyword argument(s): {names}")
    for parameter in command.parameters:
        if parameter.name in keywords:
            for value in keywords.pop(parameter.name):
                result.extend(_structured_value_tokens(parameter, value))
            continue
        if pending is None:
            continue
        result.extend(_structured_value_tokens(parameter, pending))
        pending = next(values, None)
    if pending is not None:
        result.append(pending)
        result.extend(values)
    return result
