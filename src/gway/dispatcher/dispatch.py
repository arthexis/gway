from __future__ import annotations

import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

from ..adapters import AdapterArgumentError, AdapterRegistry
from ..adapters.base import SigilContextAdapter
from ..chain_context import current_chain_context
from ..command import Command, Parameter
from ..explain import record
from ..expression import MANAGED_CHAIN_PROJECT, MANAGED_EXPRESSION_PROJECT, parse_managed_branches
from ..outcome import CommandOutcome, resolve_outcome
from ..registry import Registry, RegistryError
from ..sigils import RESERVED_CONTEXT_KEYS
from ..stage import decode_stage_escapes
from .arguments import _decode_structured_argv, _fill_context_options
from .errors import CommandNotFound, DispatchError, InvocationArgumentError
from .invocation import named_arguments_to_argv
from .prompt import _fill_required_options
from .resolution import resolve_command, resolve_default_command

_REDACTED_RESULT = "<redacted>"
_redact_command_result: ContextVar[bool] = ContextVar(
    "gway_redact_command_result", default=False
)


def _dispatcher_package():
    return sys.modules[__package__]


@contextmanager
def redact_command_results() -> Iterator[None]:
    """Keep a command result available to its caller while hiding it from event logs."""
    token = _redact_command_result.set(True)
    try:
        yield
    finally:
        _redact_command_result.reset(token)


def _logged_result(value: object) -> object:
    return _REDACTED_RESULT if _redact_command_result.get() else value


def _strict_fallback_missing(value: object) -> bool:
    return value is None or (isinstance(value, (set, frozenset)) and not value)


def _fill_python_string_defaults(
    command: Command,
    argv: Sequence[str],
) -> tuple[list[str], dict[str, str]]:
    """Inject omitted Python string defaults as attached option values."""
    result = list(argv)
    filled: dict[str, str] = {}
    for parameter in command.parameters:
        if not isinstance(parameter.default, str):
            continue
        option = next((name for name in parameter.options if name.startswith("--")), None)
        if option is None:
            option = f"--{parameter.name.replace('_', '-')}"
        negative_options = parameter.negative_options or ()
        if (
            option in result
            or any(token.startswith(f"{option}=") for token in result)
            or any(negative in result for negative in negative_options)
        ):
            continue
        result.append(f"{option}={parameter.default}")
        filled[parameter.name] = parameter.default
    return result, filled


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

        alias_arguments = next(
            (
                arguments
                for alias, arguments in (project.alias_arguments or {}).items()
                if alias.casefold() == project_name.casefold()
            ),
            (),
        )
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

        if project.adapter_type == "python":
            argv, default_values = _fill_python_string_defaults(command, argv)
            if default_values:
                record(
                    "arguments.defaults",
                    "filled omitted string arguments from function defaults",
                    project=project.name,
                    command=list(command.path),
                    values=default_values,
                    argv=list(argv),
                )

        if interactive:
            argv = _fill_required_options(command, argv, prompt=prompt)
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
        raw_result = adapter.run(command.path, resolved_argv)
        if isinstance(raw_result, CommandOutcome):
            record(
                "command.outcome",
                "managed command returned explicit semantic outcome",
                project=project.name,
                command=list(command.path),
                success=raw_result.success,
                result=_logged_result(raw_result.value),
                outcome_message=raw_result.message,
            )
            display_result = raw_result.value
        else:
            display_result = raw_result
        result = raw_result if preserve_outcome else resolve_outcome(raw_result)
        record(
            "command.result",
            "adapter command completed",
            project=project.name,
            command=list(command.path),
            result=_logged_result(display_result),
        )
        return result

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
        if isinstance(raw_result, CommandOutcome):
            record(
                "command.outcome",
                "managed command returned explicit semantic outcome",
                project=project.name,
                command=list(command.path),
                success=raw_result.success,
                result=_logged_result(raw_result.value),
                outcome_message=raw_result.message,
            )
            display_result = raw_result.value
        else:
            display_result = raw_result
        result = resolve_outcome(raw_result)
        record(
            "command.result",
            "adapter command completed",
            project=project.name,
            command=list(command.path),
            result=_logged_result(display_result),
        )
        return result

    def describe(self, project_name: str, path: tuple[str, ...]) -> Command:
        adapter = self._adapter(project_name)
        return adapter.describe(path)
