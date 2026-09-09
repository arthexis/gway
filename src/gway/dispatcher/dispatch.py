from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..adapters import AdapterRegistry
from ..adapters.base import SigilContextAdapter
from ..command import Command
from ..expression import MANAGED_EXPRESSION_PROJECT, parse_managed_branches
from ..registry import Registry, RegistryError
from . import capture_cli_values, resolve_captured_cli_values
from .arguments import _decode_structured_argv
from .errors import CommandNotFound, DispatchError
from .prompt import _fill_required_options


def _strict_fallback_missing(value: object) -> bool:
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
        commands: Sequence[Command], tokens: Sequence[str]
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
        adapter = self._adapter(project_name)
        return tuple(adapter.commands())

    def _run_expression(self, expression: str, *, interactive: bool) -> object:
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
                result = self.run(branch.project or "", branch.args, interactive=interactive)
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
            command, argv = self._resolve_default_command(commands, project.default_command, tokens)
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
