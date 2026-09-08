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


def _option_present(argv: Sequence[str], parameter: Parameter) -> bool:
    for option in _option_names(parameter):
        negative = f"--no-{option[2:]}" if option.startswith("--") else ""
        for token in argv:
            if token == option or token.startswith(f"{option}="):
                return True
            if negative and token == negative:
                return True
    return False


def _read_prompt(prompt: str) -> str:
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def _prompt_value(parameter: Parameter) -> list[str]:
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


def _fill_required_options(command: Command, argv: list[str]) -> list[str]:
    completed = list(argv)
    for parameter in command.parameters:
        if not parameter.required or parameter.positional or _option_present(completed, parameter):
            continue
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
    keywords: dict[str, str] = {}
    ordinary: list[str] = []

    for token in argv:
        if token.startswith(STRUCTURED_ARG_PREFIX):
            positional.append(token[len(STRUCTURED_ARG_PREFIX) :])
            continue
        if token.startswith(STRUCTURED_KWARG_PREFIX):
            payload = token[len(STRUCTURED_KWARG_PREFIX) :]
            name, separator, value = payload.partition("=")
            if not separator:
                raise DispatchError(f"invalid structured keyword argument: {payload!r}")
            keywords[name] = value
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
            result.extend(_structured_value_tokens(parameter, keywords.pop(parameter.name)))
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
        command, argv = self._resolve_command(commands, tokens)
        argv = _decode_structured_argv(command, argv)
        if interactive:
            argv = _fill_required_options(command, argv)

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
