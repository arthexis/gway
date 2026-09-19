"""Argument binding and value conversion for GWAY callables."""

import inspect
import re
from dataclasses import dataclass

from .sigil import Sigil
from .tokens import Token, is_literal, token_value


_NO_PIPELINE = object()
_CHAIN_SELECTOR = re.compile(r"^\[\s*(\*|[+-]?\d+)\s*\]$")


class Literal(str):
    """String value protected from signature-based coercion."""


@dataclass(frozen=True)
class BoundCall:
    args: tuple
    kwargs: dict


@dataclass(frozen=True)
class _PipelineValue:
    value: object


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


def _pipeline_bundle(value):
    return tuple(value) if isinstance(value, tuple) else (value,)


def _chain_selector(token):
    if is_literal(token):
        return None
    value = token_value(token)
    if not isinstance(value, str):
        return None
    match = _CHAIN_SELECTOR.fullmatch(value)
    return match.group(1) if match else None


def _normalize_pipeline_index(index, size):
    original = index
    if index < 0:
        index += size
    if index < 0 or index >= size:
        raise IndexError(f"Pipeline result index {original} is out of range")
    return index


def _compose_pipeline_stream(tokens, pipeline):
    """Place chain-local selectors against one immutable pipeline snapshot."""
    bundle = _pipeline_bundle(pipeline)
    tokens = list(tokens)

    numeric = []
    star_count = 0
    for token in tokens:
        selector = _chain_selector(token)
        if selector is None:
            continue
        if selector == "*":
            star_count += 1
            continue
        numeric.append(_normalize_pipeline_index(int(selector), len(bundle)))

    if star_count > 1:
        raise ValueError("Chain positional selector [*] may appear only once")

    consumed = set(numeric)
    remaining = [
        _PipelineValue(value)
        for index, value in enumerate(bundle)
        if index not in consumed
    ]

    composed = []
    for token in tokens:
        selector = _chain_selector(token)
        if selector is None:
            composed.append(token)
            continue
        if selector == "*":
            composed.extend(remaining)
            continue
        index = _normalize_pipeline_index(int(selector), len(bundle))
        composed.append(_PipelineValue(bundle[index]))

    if star_count == 0:
        composed = [*remaining, *composed]

    return composed

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
    pipeline=_NO_PIPELINE,
) -> BoundCall:
    """Bind explicit tokens and optional raw chain positionals to one callable."""
    signature = inspect.signature(func)
    keywords = {} if initial_kwargs is None else dict(initial_kwargs)
    stream = list(tokens)
    if pipeline is not _NO_PIPELINE:
        stream = _compose_pipeline_stream(stream, pipeline)

    converted_positional = list(initial_args)
    filled = _initial_filled(signature, converted_positional, keywords)
    greedy = _greedy_parameter(signature)
    literal_mode = False
    index = 0

    while index < len(stream):
        item = stream[index]
        parameter = _next_positional(signature, filled)

        if isinstance(item, _PipelineValue):
            converted_positional.append(item.value)
            if parameter is not None and parameter.kind is not inspect.Parameter.VAR_POSITIONAL:
                filled.add(parameter.name)
            index += 1
            continue

        token = token_value(item)

        if not literal_mode and not is_literal(item) and token == "--":
            literal_mode = True
            index += 1
            continue

        if not literal_mode and not is_literal(item) and token.startswith("--"):
            key = token[2:].replace("-", "_")
            keyword_parameter = signature.parameters.get(key)
            if keyword_parameter is None:
                raise TypeError(f"Unknown argument --{key.replace('_', '-')}")
            if (
                keyword_parameter.annotation is bool
                or isinstance(keyword_parameter.default, bool)
            ):
                keywords[key] = True
                filled.add(key)
                index += 1
                continue
            if index + 1 >= len(stream):
                raise TypeError(f"Expected a value after {token}")
            value_item = stream[index + 1]
            if isinstance(value_item, _PipelineValue):
                keywords[key] = value_item.value
            else:
                keywords[key] = convert_argument(
                    value_item,
                    keyword_parameter,
                    runtime,
                )
            filled.add(key)
            index += 2
            continue

        if greedy is not None and parameter is greedy:
            tail = stream[index:]
            if any(isinstance(part, _PipelineValue) for part in tail):
                raise TypeError(
                    "Pipeline positional values cannot be inserted after "
                    "a greedy string argument has started"
                )
            parts = [convert_argument(part, greedy, runtime) for part in tail]
            converted_positional.append(" ".join(str(part) for part in parts))
            filled.add(greedy.name)
            break

        if parameter is None:
            converted_positional.append(token)
        else:
            converted_positional.append(convert_argument(item, parameter, runtime))
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

