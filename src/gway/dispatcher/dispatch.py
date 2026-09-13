from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from ..adapters import AdapterRegistry
from ..adapters.base import SigilContextAdapter
from ..chain_context import current_chain_context
from ..command import Command, command_path_aliases
from ..explain import record
from ..expression import MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT, parse_managed_branches
from ..registry import Registry, RegistryError
from ..sigils import RESERVED_CONTEXT_KEYS
from ..stage import decode_stage_escapes
from .arguments import _decode_structured_argv, _fill_context_options
from .errors import CommandNotFound, DispatchError
from .prompt import _fill_required_options


def _dispatcher_package():
    return sys.modules[__package__]


def _strict_fallback_missing(value: object) -> bool:
    return value is None or (isinstance(value, (set, frozenset)) and not value)


def _command_key(value: str) -> str:
    """Return the normalized lookup spelling for one command-path component."""
    return value.replace("_", "-")


def _command_path_key(path: Sequence[str]) -> tuple[str, ...]:
    """Normalize command-path spelling while leaving argument values untouched."""
    return tuple(_command_key(part) for part in path)


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
        adapter = self.adapters.create(project)
        record(
            "adapter.select",
            "selected project adapter",
            project=project.name,
            adapter=project.adapter_type,
        )
        return adapter

    @staticmethod
    def _resolve_command(
        commands: Sequence[Command], tokens: Sequence[str]
    ) -> tuple[Command, list[str]]:
        normalized_tokens = _command_path_key(tokens)
        matches = [
            command
            for command in commands
            if len(tokens) >= len(command.path)
            and normalized_tokens[: len(command.path)] == _command_path_key(command.path)
        ]
        resolution = "exact"
        if not matches:
            matches = [
                command
                for command in commands
                if len(tokens) >= len(command.path)
                and normalized_tokens[: len(command.path)] in command_path_aliases(command.path)[1:]
            ]
            resolution = "alias"
        if not matches:
            requested = " ".join(tokens) if tokens else "<command>"
            record("command.resolve", "command resolution failed", requested=requested)
            raise CommandNotFound(f"unknown command: {requested}")
        command = max(matches, key=lambda item: len(item.path))
        record(
            "command.resolve",
            "resolved managed command",
            requested=list(tokens),
            selected=list(command.path),
            resolution=resolution,
        )
        return command, list(tokens[len(command.path) :])

    @staticmethod
    def _resolve_default_command(
        commands: Sequence[Command],
        default_path: tuple[str, ...],
        tokens: Sequence[str],
    ) -> tuple[Command, list[str]]:
        normalized_default = _command_path_key(default_path)
        for command in commands:
            if _command_path_key(command.path) == normalized_default:
                record(
                    "command.resolve",
                    "resolved configured default command",
                    requested=list(tokens),
                    selected=list(command.path),
                    resolution="default",
                )
                return command, list(tokens)
        record(
            "command.resolve",
            "configured default command was not found",
            selected=list(default_path),
            resolution="default",
        )
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
        record("dispatch.start", "dispatching project", project=project_name, tokens=list(tokens))
        if project_name == MANAGED_CHAIN_PROJECT:
            from ..chain import run_chain

            return run_chain(self, tokens, interactive=interactive)
        if project_name == MANAGED_EXPRESSION_PROJECT:
            if len(tokens) != 1:
                raise DispatchError("managed expression dispatch expects one expression")
            return self._run_expression(tokens[0], interactive=interactive)
        project = self.registry.require(project_name)
        adapter = self.adapters.create(project)
        record(
            "adapter.select",
            "selected project adapter",
            project=project.name,
            adapter=project.adapter_type,
        )
        commands = tuple(adapter.commands())
        try:
            command, argv = self._resolve_command(commands, tokens)
        except CommandNotFound:
            if not project.default_command:
                raise
            command, argv = self._resolve_default_command(commands, project.default_command, tokens)

        alias_arguments = (project.alias_arguments or {}).get(project_name, ())
        if alias_arguments:
            record(
                "arguments.alias",
                "prepended alias-bound arguments",
                project=project.name,
                arguments=list(alias_arguments),
            )

        argv = list(decode_stage_escapes((*alias_arguments, *argv)))
        record(
            "arguments.raw",
            "collected command arguments",
            project=project.name,
            command=list(command.path),
            argv=list(argv),
        )

        chain_context = current_chain_context()
        argument_context = {
            key: value
            for key, value in chain_context.items()
            if key not in RESERVED_CONTEXT_KEYS and key != "result"
        }
        argv, context_values = _fill_context_options(command, argv, argument_context)
        if context_values:
            record(
                "arguments.context",
                "filled command arguments from active context",
                project=project.name,
                command=list(command.path),
                values=context_values,
                argv=list(argv),
            )

        if interactive:
            argv = _fill_required_options(command, argv)
            record(
                "arguments.interactive",
                "filled interactive command arguments",
                project=project.name,
                command=list(command.path),
                argv=list(argv),
            )

        decoded_argv = _decode_structured_argv(command, argv)
        record(
            "arguments.decode",
            "decoded structured command arguments",
            project=project.name,
            command=list(command.path),
            before=list(argv),
            after=list(decoded_argv),
        )
        argv = decoded_argv

        dispatcher_package = _dispatcher_package()
        templates = dispatcher_package.capture_cli_values(argv, paths=self.registry.paths)
        record(
            "sigil.capture",
            "captured command argument templates",
            project=project.name,
            command=list(command.path),
            argv=list(argv),
        )
        extra_context: dict[str, object] = {}
        if isinstance(adapter, SigilContextAdapter):
            provided_context = adapter.sigil_context(command.path)
            if not isinstance(provided_context, Mapping):
                raise DispatchError("adapter sigil_context() must return a mapping")
            extra_context.update(provided_context)
            record(
                "sigil.context",
                "added adapter-provided Sigil context",
                project=project.name,
                command=list(command.path),
                keys=sorted(str(key) for key in provided_context),
            )
        extra_context.update(
            (key, value) for key, value in chain_context.items() if key not in RESERVED_CONTEXT_KEYS
        )
        try:
            resolved_argv = dispatcher_package.resolve_captured_cli_values(
                templates,
                project,
                command.path,
                paths=self.registry.paths,
                extra_context=extra_context or None,
            )
        except ValueError as exc:
            record(
                "sigil.resolve",
                "Sigil resolution failed",
                project=project.name,
                command=list(command.path),
                error=str(exc),
            )
            raise DispatchError(str(exc)) from exc
        record(
            "sigil.resolve",
            "resolved command argument templates",
            project=project.name,
            command=list(command.path),
            before=list(argv),
            after=list(resolved_argv),
        )
        record(
            "command.bind",
            "bound resolved CLI arguments to adapter command",
            project=project.name,
            command=list(command.path),
            argv=list(resolved_argv),
        )
        record(
            "command.call",
            "invoking adapter command",
            project=project.name,
            command=list(command.path),
            argv=list(resolved_argv),
        )
        result = adapter.run(command.path, resolved_argv)
        record(
            "command.result",
            "adapter command completed",
            project=project.name,
            command=list(command.path),
            result=result,
        )
        return result

    def describe(self, project_name: str, path: tuple[str, ...]) -> Command:
        adapter = self._adapter(project_name)
        return adapter.describe(path)
