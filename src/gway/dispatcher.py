from __future__ import annotations

from collections.abc import Mapping, Sequence

from .adapters import AdapterRegistry
from .adapters.base import SigilContextAdapter
from .command import Command
from .registry import Registry
from .sigils import capture_cli_values, resolve_captured_cli_values


class DispatchError(ValueError):
    pass


class CommandNotFound(DispatchError):
    pass


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

    def run(self, project_name: str, tokens: Sequence[str]) -> object:
        project = self.registry.require(project_name)
        adapter = self.adapters.create(project)
        commands = tuple(adapter.commands())
        command, argv = self._resolve_command(commands, tokens)

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
