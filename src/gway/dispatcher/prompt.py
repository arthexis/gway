from __future__ import annotations

import sys

from ..command import Command, Parameter
from ..expression import STRUCTURED_KWARG_PREFIX
from .arguments import (
    _provided_positional_count,
    _required_positional_count,
    _structured_keyword_counts,
    _trailing_variadic_option,
)
from .errors import DispatchError
from .options import _negative_option_names, _option_name, _option_present


def _read_prompt(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def _prompt_value(parameter: Parameter) -> list[str]:
    if parameter.positional:
        while True:
            value = _read_prompt(f"{parameter.name}: ")
            if value:
                return [value]
            print("A value is required.", file=sys.stderr)
    option = _option_name(parameter)
    if parameter.annotation is bool:
        while True:
            answer = _read_prompt(f"{parameter.name} [y/n]: ").strip().lower()
            if answer in {"y", "yes", "1", "true", "on"}:
                return [option]
            if answer in {"n", "no", "0", "false", "off"}:
                negative_options = _negative_option_names(parameter)
                if negative_options:
                    return [negative_options[0]]
                if option.startswith("--"):
                    raise DispatchError(f"{parameter.name} has no unambiguous negative option")
                return [option, "false"]
            print("Please answer yes or no.", file=sys.stderr)
    while True:
        value = _read_prompt(f"{parameter.name}: ")
        if value:
            return [option, value]
        print("A value is required.", file=sys.stderr)


def _fill_required_options(command: Command, argv: list[str]) -> list[str]:
    completed = list(argv)
    structured_counts = _structured_keyword_counts(completed)
    structured_names = set(structured_counts)
    provided_positionals = _provided_positional_count(command, completed)
    trailing_variadic = _trailing_variadic_option(command, completed)
    inserted_literal_separator = False
    for parameter in command.parameters:
        if not parameter.required:
            continue
        if parameter.positional:
            required_count = _required_positional_count(parameter)
            structured_supplied = min(structured_counts.get(parameter.name, 0), required_count)
            ordinary_capacity = required_count - structured_supplied
            ordinary_supplied = min(provided_positionals, ordinary_capacity)
            provided_positionals -= ordinary_supplied
            missing = required_count - structured_supplied - ordinary_supplied
            if not missing:
                continue
            if trailing_variadic and "--" not in completed:
                completed.append("--")
                inserted_literal_separator = True
                trailing_variadic = False
            for _ in range(missing):
                prompted = _prompt_value(parameter)[0]
                if structured_names and not inserted_literal_separator:
                    completed.append(f"{STRUCTURED_KWARG_PREFIX}{parameter.name}={prompted}")
                    structured_names.add(parameter.name)
                    structured_counts[parameter.name] = structured_counts.get(parameter.name, 0) + 1
                else:
                    completed.append(prompted)
            continue
        if parameter.name in structured_names:
            continue
        if not _option_present(completed, parameter):
            completed.extend(_prompt_value(parameter))
    return completed
