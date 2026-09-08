from __future__ import annotations

from collections.abc import Sequence

from .adapters import AdapterRegistry
from .command import Command, Parameter
from .registry import Registry
from .sigils import resolve_cli_values


class DispatchError(ValueError):
    pass


class CommandNotFound(DispatchError):
    pass


def _option_name(parameter: Parameter) -> str:
    if parameter.options:
        long_options = [option for option in parameter.options if option.startswith("--")]
        if long_options:
            return long_options[0]
        return parameter.options[0]
    return f"--{parameter.name.replace('_', '-')}"


def _option_present(argv: Sequence[str], parameter: Parameter) -> bool:
    option = _option_name(parameter)
    negative = f"--no-{option[2:]}" if option.startswith("--") else ""
    for token in argv:
        if token == option or token.startswith(f"{option}="):
            return True
        if negative and token == negative:
            return True
    return False


def _prompt_value(parameter: Parameter) -> list[str]:
    option = _option_name(parameter)
    if parameter.annotation is bool:
        while True:
            answer = input(f"{parameter.name} [y/n]: ").strip().lower()
            if answer in {"y", "yes", "1", "true", "on"}:
                return [option]
            if answer in {"n", "no", "0", "false", "off"}:
                if option.startswith("--"):
                    return [f"--no-{option[2:]}"]
                return [option, "false"]
            print("Please answer yes or no.")

    while True:
        value = input(f"{parameter.name}: ")
        if value:
            return [option, value]
        print("A value is required.")


def _fill_required_options(command: Command, argv: list[str]) -> list[str]:
    completed = list(argv)
    for parameter in command.parameters:
        if not parameter.required or parameter.positional or _option_present(completed, parameter):
            continue
        completed.extend(_prompt_value(parameter))
    return completed


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

    def run(
        self,
        project_name: str,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
    ) -> object:
        project = self.registry.require(project_name)
        adapter = self.adapters.create(project)
        commands = tuple(adapter.commands())
        command, argv = self._resolve_command(commands, tokens)
        if interactive:
            argv = _fill_required_options(command, argv)
        resolved_argv = resolve_cli_values(
            argv,
            project,
            command.path,
            paths=self.registry.paths,
        )
        return adapter.run(command.path, resolved_argv)

    def describe(self, project_name: str, path: tuple[str, ...]) -> Command:
        adapter = self._adapter(project_name)
        return adapter.describe(path)
