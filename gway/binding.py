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


def _positional_parameters(signature):
    return [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]


def _variadic_parameter(signature):
    return next(
        (
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL
        ),
        None,
    )


def _greedy_parameter(signature):
    """Return the final positional string parameter when it can own a free-form tail."""
    if _variadic_parameter(signature) is not None:
        return None
    positional = _positional_parameters(signature)
    if positional and positional[-1].annotation is str:
        return positional[-1]
    return None


def _next_positional(signature, filled):
    for parameter in _positional_parameters(signature):
        if parameter.name not in filled:
            return parameter
    return _variadic_parameter(signature)


def _initial_filled(signature, initial_args=(), initial_kwargs=None):
    bound = signature.bind_partial(
        *tuple(initial_args),
        **({} if initial_kwargs is None else dict(initial_kwargs)),
    )
    return set(bound.arguments)


def pipeline_boundary(
    func,
    tokens,
    *,
    initial_args=(),
    initial_kwargs=None,
):
    """Return the first structural pipeline dash outside a greedy string tail."""
    signature = inspect.signature(func)
    filled = _initial_filled(signature, initial_args, initial_kwargs)
    greedy = _greedy_parameter(signature)
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
                return None
            filled.add(key)
            if parameter.annotation is bool or isinstance(parameter.default, bool):
                index += 1
            else:
                if index + 1 >= len(tokens):
                    return None
                index += 2
            continue

        parameter = _next_positional(signature, filled)
        if greedy is not None and parameter is greedy:
            return None

        if not is_literal(raw) and token == "-":
            return index

        if parameter is not None and parameter.kind is not inspect.Parameter.VAR_POSITIONAL:
            filled.add(parameter.name)
        index += 1

    return None


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
    keywords = {} if initial_kwargs is None else dict(initial_kwargs)
    converted_positional = list(initial_args)
    filled = _initial_filled(signature, initial_args, keywords)
    greedy = _greedy_parameter(signature)
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
            filled.add(key)
            if parameter.annotation is bool or isinstance(parameter.default, bool):
                keywords[key] = True
                index += 1
                continue
            if index + 1 >= len(tokens):
                raise TypeError(f"Expected a value after {token}")
            keywords[key] = convert_argument(tokens[index + 1], parameter, runtime)
            index += 2
            continue

        parameter = _next_positional(signature, filled)

        if greedy is not None and parameter is greedy:
            parts = [
                convert_argument(item, greedy, runtime)
                for item in tokens[index:]
            ]
            converted_positional.append(" ".join(str(part) for part in parts))
            filled.add(greedy.name)
            index = len(tokens)
            break

        if parameter is None:
            converted_positional.append(token_value(raw))
        else:
            converted_positional.append(convert_argument(raw, parameter, runtime))
            if parameter.kind is not inspect.Parameter.VAR_POSITIONAL:
                filled.add(parameter.name)
        index += 1

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
