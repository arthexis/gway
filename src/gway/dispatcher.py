from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from .adapters import AdapterRegistry
from .adapters.base import SigilContextAdapter
from .command import Command, Parameter
from .expression import (
    MANAGED_EXPRESSION_PROJECT,
    STRUCTURED_ARG_PREFIX,
    STRUCTURED_KWARG_PREFIX,
    parse_managed_branches,
)
from .registry import Registry, RegistryError
from .sigils import capture_cli_values, resolve_captured_cli_values


class DispatchError(ValueError):
    pass


class CommandNotFound(DispatchError):
    pass


def _option_names(parameter: Parameter) -> tuple[str, ...]:
    if parameter.options:
        return parameter.options
    return (f"--{parameter.name.replace('_', '-')}",)


def _option_name(parameter: Parameter) -> str:
    options = _option_names(parameter)
    long_options = [option for option in options if option.startswith("--")]
    if long_options:
        return long_options[0]
    return options[0]


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
        negative = f"--no-{option[2:]}" if option.startswith("--") else ""
        for token in argv:
            if token == option or token.startswith(f"{option}="):
                return True
            if _abbreviated_long_option(token, option):
                return True
            if _attached_short_option(token, option, parameter):
                return True
            if negative and token == negative:
                return True
    return False


def _option_consumes_value(parameter: Parameter) -> bool:
    if parameter.consumes_value is not None:
        return parameter.consumes_value
    return parameter.annotation is not bool


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
                if option.startswith("--"):
                    return [f"--no-{option[2:]}"]
                return [option, "false"]
            print("Please answer yes or no.", file=sys.stderr)

    while True:
        value = _read_prompt(f"{parameter.name}: ")
        if value:
            return [option, value]
        print("A value is required.", file=sys.stderr)


def _match_option(
    token: str,
    option_parameters: Mapping[str, Parameter],
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


def _option_value_count(
    parameter: Parameter,
    argv: Sequence[str],
    start: int,
    option_parameters: Mapping[str, Parameter],
) -> int:
    arity = parameter.option_arity
    if isinstance(arity, int):
        return max(0, min(arity, len(argv) - start))
    if arity in {"*", "+"}:
        count = 0
        while start + count < len(argv):
            token = argv[start + count]
            matched, _ = _match_option(token, option_parameters)
            if token == "--" or matched is not None:
                break
            count += 1
        return count
    if arity == "?":
        if start >= len(argv):
            return 0
        token = argv[start]
        matched, _ = _match_option(token, option_parameters)
        return 0 if token == "--" or matched is not None else 1
    return 1 if _option_consumes_value(parameter) and start < len(argv) else 0


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


def _structured_keyword_names(argv: Sequence[str]) -> set[str]:
    return set(_structured_keyword_counts(argv))


def _option_parameters(command: Command) -> dict[str, Parameter]:
    result: dict[str, Parameter] = {}
    for parameter in command.parameters:
        if parameter.positional:
            continue
        for option in _option_names(parameter):
            result[option] = parameter
            if parameter.annotation is bool and option.startswith("--"):
                result[f"--no-{option[2:]}"] = parameter
    return result


def _provided_positional_count(command: Command, argv: Sequence[str]) -> int:
    option_parameters = _option_parameters(command)
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
            parameter, attached = _match_option(token, option_parameters)
            if parameter is not None:
                index += 1
                if not attached:
                    index += _option_value_count(parameter, argv, index, option_parameters)
                continue

        count += 1
        index += 1
    return count


def _trailing_variadic_option(command: Command, argv: Sequence[str]) -> bool:
    option_parameters = _option_parameters(command)
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
        parameter, attached = _match_option(token, option_parameters)
        if parameter is not None:
            active = parameter.option_arity in {"*", "+"}
            index += 1
            if not attached and not active:
                index += _option_value_count(parameter, argv, index, option_parameters)
            continue
        index += 1
    return active


def _required_positional_count(parameter: Parameter) -> int:
    arity = parameter.option_arity
    if isinstance(arity, int):
        return max(1, arity)
    if arity == "+":
        return 1
    return 1


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


def _structured_value_tokens(parameter: Parameter, value: str) -> list[str]:
    """Translate one structured value to this command's normal CLI spelling."""
    if parameter.positional:
        return [value]

    option = _option_name(parameter)
    if parameter.annotation is bool:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return [option]
        if normalized in {"0", "false", "no", "off"}:
            return [f"--no-{option[2:]}"] if option.startswith("--") else [option, "false"]
    return [option, value]


def _decode_structured_argv(command: Command, argv: Sequence[str]) -> list[str]:
    """Bind colon-delimited positional/keyword values to command parameters."""
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


def _strict_fallback_missing(value: object) -> bool:
    """Return whether a resolved CLI result should advance across ``||``."""
    return value is None or (isinstance(value, (set, frozenset)) and not value)


class Dispatcher:
    """Resolve registered projects, adapters, managed commands, and CLI sigils."""

    def __init__(
        self,
        registry: Registry | None = None,
        adapters: AdapterRegistry | None = None,
    ) -> None:
        self.registry = registry or Registry()
        self.adapters = adapters or AdapterRegistry()

    def _adapter(self, project_name: str):
        project = self.registry.require(project_name)
        return self.adapters.create(project)

    @staticmethod
    def _resolve_command(
        commands: Sequence[Command],
        tokens: Sequence[str],
    ) -> tuple[Command, list[str]]:
        matches = [
            command
            for command in commands
            if len(tokens) >= len(command.path)
            and tuple(tokens[: len(command.path)]) == command.path
        ]
        if not matches:
            requested = " ".join(tokens) if tokens else "<command>"
            raise CommandNotFound(f"unknown command: {requested}")
        command = max(matches, key=lambda item: len(item.path))
        return command, list(tokens[len(command.path) :])

    @staticmethod
    def _resolve_default_command(
        commands: Sequence[Command],
        default_path: tuple[str, ...],
        tokens: Sequence[str],
    ) -> tuple[Command, list[str]]:
        for command in commands:
            if command.path == default_path:
                return command, list(tokens)
        raise CommandNotFound(f"configured default command not found: {' '.join(default_path)}")

    def commands(self, project_name: str) -> tuple[Command, ...]:
        """Return the discovered command surface for one managed project."""
        adapter = self._adapter(project_name)
        return tuple(adapter.commands())

    def _run_expression(self, expression: str, *, interactive: bool) -> object:
        """Evaluate calls plus loose ``|`` and strict ``||`` fallbacks."""
        branches = parse_managed_branches(expression)
        result: object = None
        resolved = False
        last_missing: Exception | None = None

        for index, branch in enumerate(branches):
            if index:
                should_fallback = (
                    not resolved or _strict_fallback_missing(result)
                    if branch.operator == "||"
                    else not resolved or not bool(result)
                )
                if not should_fallback:
                    return result

            if branch.is_literal:
                return branch.literal

            try:
                result = self.run(
                    branch.project or "",
                    branch.args,
                    interactive=interactive,
                )
            except (CommandNotFound, RegistryError) as exc:
                last_missing = exc
                resolved = False
                continue

            resolved = True

        if resolved:
            return result
        if last_missing is not None:
            raise last_missing
        return None

    def run(
        self,
        project_name: str,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
    ) -> object:
        if project_name == MANAGED_EXPRESSION_PROJECT:
            if len(tokens) != 1:
                raise DispatchError("managed expression dispatch expects one expression")
            return self._run_expression(tokens[0], interactive=interactive)

        project = self.registry.require(project_name)
        adapter = self.adapters.create(project)
        commands = tuple(adapter.commands())
        try:
            command, argv = self._resolve_command(commands, tokens)
        except CommandNotFound:
            if not project.default_command:
                raise
            command, argv = self._resolve_default_command(
                commands,
                project.default_command,
                tokens,
            )
        if interactive:
            argv = _fill_required_options(command, argv)
        argv = _decode_structured_argv(command, argv)

        templates = capture_cli_values(argv, paths=self.registry.paths)
        extra_context: dict[str, object] | None = None
        if isinstance(adapter, SigilContextAdapter):
            provided_context = adapter.sigil_context(command.path)
            if not isinstance(provided_context, Mapping):
                raise DispatchError("adapter sigil_context() must return a mapping")
            extra_context = dict(provided_context)

        try:
            resolved_argv = resolve_captured_cli_values(
                templates,
                project,
                command.path,
                paths=self.registry.paths,
                extra_context=extra_context,
            )
        except ValueError as exc:
            raise DispatchError(str(exc)) from exc
        return adapter.run(command.path, resolved_argv)

    def describe(self, project_name: str, path: tuple[str, ...]) -> Command:
        adapter = self._adapter(project_name)
        return adapter.describe(path)
