from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from ..adapters import AdapterArgumentError, AdapterRegistry
from ..chain_context import current_chain_context
from ..command import Command
from ..explain import record
from ..expression import MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT, parse_managed_branches
from ..registry import Registry, RegistryError
from .binding import bind_command_arguments
from .errors import CommandNotFound, DispatchError, InvocationArgumentError
from .invocation import named_arguments_to_argv
from .outcome import finalize_command_result
from .resolution import resolve_command, resolve_default_command
from .sigils import resolve_dispatch_arguments


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
        adapter = self.adapters.create(project)
        record(
            "adapter.select",
            "selected project adapter",
            project=project.name,
            adapter=project.adapter_type,
        )
        return adapter

    def commands(self, project_name: str) -> tuple[Command, ...]:
        adapter = self._adapter(project_name)
        return tuple(adapter.commands())

    def _run_expression(
        self,
        expression: str,
        *,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
    ) -> object:
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
            try:
                if prompt is None:
                    result = self.run(
                        branch.project,
                        branch.args,
                        interactive=interactive,
                    )
                else:
                    result = self.run(
                        branch.project,
                        branch.args,
                        interactive=interactive,
                        prompt=prompt,
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
        prompt: Callable[[str], str] | None = None,
        preserve_outcome: bool = False,
    ) -> object:
        record("dispatch.start", "dispatching project", project=project_name, tokens=list(tokens))
        if project_name == MANAGED_CHAIN_PROJECT:
            from ..chain import run_chain

            return run_chain(self, tokens, interactive=interactive, prompt=prompt)
        if project_name == MANAGED_EXPRESSION_PROJECT:
            if len(tokens) != 1:
                raise DispatchError("managed expression dispatch expects one expression")
            return self._run_expression(tokens[0], interactive=interactive, prompt=prompt)
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
            command, argv = resolve_command(commands, tokens)
        except CommandNotFound:
            if not project.default_command:
                raise
            command, argv = resolve_default_command(commands, project.default_command, tokens)

        chain_context = current_chain_context()
        argv = bind_command_arguments(
            project=project,
            requested_project_name=project_name,
            command=command,
            argv=argv,
            chain_context=chain_context,
            interactive=interactive,
            prompt=prompt,
        )

        resolved_argv = resolve_dispatch_arguments(
            argv,
            project=project,
            command=command,
            adapter=adapter,
            chain_context=chain_context,
            paths=self.registry.paths,
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
        raw_result = adapter.run(command.path, resolved_argv)
        return finalize_command_result(
            raw_result,
            project=project,
            command=command,
            preserve_outcome=preserve_outcome,
        )

    def invoke(
        self,
        project_name: str,
        command_path: Sequence[str],
        arguments: Mapping[str, str] | None = None,
    ) -> object:
        """Invoke exactly one managed command from literal named string arguments."""
        if project_name in {MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT}:
            raise DispatchError("programmatic invocation does not support managed programs")
        if not command_path:
            raise DispatchError("programmatic invocation requires a command path")

        project = self.registry.require(project_name)
        adapter = self.adapters.create(project)
        record(
            "invoke.start",
            "invoking one managed command programmatically",
            project=project.name,
            requested_project=project_name,
            command=list(command_path),
        )
        record(
            "adapter.select",
            "selected project adapter",
            project=project.name,
            adapter=project.adapter_type,
        )

        command, remainder = resolve_command(tuple(adapter.commands()), command_path)
        if remainder:
            requested = " ".join(command_path)
            raise DispatchError(
                f"programmatic command path must identify exactly one command: {requested}"
            )

        argv = named_arguments_to_argv(command, arguments or {})
        alias_arguments = (project.alias_arguments or {}).get(project_name.casefold(), ())
        if alias_arguments:
            record(
                "arguments.alias",
                "prepended alias-bound arguments",
                project=project.name,
                arguments=list(alias_arguments),
            )
        argv = [*alias_arguments, *argv]
        record(
            "arguments.literal",
            "bound literal programmatic arguments",
            project=project.name,
            command=list(command.path),
            argv=list(argv),
        )
        record(
            "command.call",
            "invoking adapter command",
            project=project.name,
            command=list(command.path),
            argv=list(argv),
        )
        try:
            raw_result = adapter.run(command.path, argv)
        except AdapterArgumentError as exc:
            raise InvocationArgumentError(str(exc)) from exc
        return finalize_command_result(
            raw_result,
            project=project,
            command=command,
        )

    def describe(self, project_name: str, path: tuple[str, ...]) -> Command:
        adapter = self._adapter(project_name)
        return adapter.describe(path)
