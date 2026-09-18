"""Argument binding and value conversion for GWAY callables."""

import inspect
from dataclasses import dataclass

from .sigil import Sigil
from .tokens import Token, is_literal, token_value


class Literal(str):
    """String value protected from signature-based coercion."""


@dataclass(frozen=True)
class BoundCall:
    args: tuple
    kwargs: dict


def convert_argument(token, parameter, runtime):
    """Convert one explicit token according to literal, sigil, and annotation rules."""
    literal = is_literal(token)
    value = token_value(token)
    annotation = parameter.annotation

    if literal:
        return Literal(value)

    if isinstance(value, str) and Sigil._pattern.search(value):
        value = runtime.resolve(value)

    if annotation in (inspect.Parameter.empty, str):
        return value
    if annotation is bool and isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if annotation in (int, float):
        return annotation(value)
    return value


def bind_arguments(
    func,
    tokens,
    *,
    runtime,
    interactive=False,
    initial_args=(),
    initial_kwargs=None,
) -> BoundCall:
    """Bind command tokens after any already-supplied native arguments."""
    signature = inspect.signature(func)
    positional = []
    keywords = {} if initial_kwargs is None else dict(initial_kwargs)
    tokens = list(tokens)
    index = 0
    literal_mode = False

    while index < len(tokens):
        raw = tokens[index]
        token = token_value(raw)

        if not literal_mode and not is_literal(raw) and token == "--":
            literal_mode = True
            index += 1
            continue

        if not literal_mode and not is_literal(raw) and token.startswith("--"):
            key = token[2:].replace("-", "_")
            parameter = signature.parameters.get(key)
            if parameter is None:
                raise TypeError(f"Unknown argument --{key.replace('_', '-')}")
            if parameter.annotation is bool or isinstance(parameter.default, bool):
                keywords[key] = True
                index += 1
                continue
            if index + 1 >= len(tokens):
                raise TypeError(f"Expected a value after {token}")
            keywords[key] = convert_argument(tokens[index + 1], parameter, runtime)
            index += 2
        else:
            positional.append(raw)
            index += 1

    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    converted_positional = list(initial_args)
    positional_offset = len(converted_positional)
    for offset, token in enumerate(positional):
        parameter_offset = positional_offset + offset
        if parameter_offset < len(positional_parameters):
            converted_positional.append(
                convert_argument(
                    token,
                    positional_parameters[parameter_offset],
                    runtime,
                )
            )
        else:
            converted_positional.append(token_value(token))

    bound = signature.bind_partial(*converted_positional, **keywords)

    if interactive:
        for name, parameter in signature.parameters.items():
            if name in bound.arguments:
                continue
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if parameter.default is not inspect.Parameter.empty:
                continue
            response = input(f"{name}: ")
            bound.arguments[name] = convert_argument(
                Token(response),
                parameter,
                runtime,
            )

    return BoundCall(bound.args, bound.kwargs)
