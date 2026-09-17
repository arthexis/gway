from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from ..command import Command
from ..explain import record
from ..project import Project
from ..sigils import RESERVED_CONTEXT_KEYS
from ..stage import decode_stage_escapes
from .arguments import _decode_structured_argv, _fill_context_options
from .prompt import _fill_required_options


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
        option = next(
            (name for name in parameter.options if name.startswith("--")),
            None,
        )
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


def bind_command_arguments(
    *,
    project: Project,
    requested_project_name: str,
    command: Command,
    argv: Sequence[str],
    chain_context: Mapping[str, object],
    interactive: bool,
    prompt: Callable[[str], str] | None = None,
) -> list[str]:
    """Prepare adapter-facing argv for one resolved managed command."""
    alias_arguments = next(
        (
            arguments
            for alias, arguments in (project.alias_arguments or {}).items()
            if alias.casefold() == requested_project_name.casefold()
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

    bound = list(decode_stage_escapes((*alias_arguments, *argv)))
    record(
        "arguments.raw",
        "collected command arguments",
        project=project.name,
        command=list(command.path),
        argv=list(bound),
    )

    argument_context = {
        key: value
        for key, value in chain_context.items()
        if key not in RESERVED_CONTEXT_KEYS and key != "result"
    }
    bound, context_values = _fill_context_options(
        command,
        bound,
        argument_context,
    )
    if context_values:
        record(
            "arguments.context",
            "filled command arguments from active context",
            project=project.name,
            command=list(command.path),
            values=context_values,
            argv=list(bound),
        )

    if project.adapter_type == "python":
        bound, default_values = _fill_python_string_defaults(command, bound)
        if default_values:
            record(
                "arguments.defaults",
                "filled omitted string arguments from function defaults",
                project=project.name,
                command=list(command.path),
                values=default_values,
                argv=list(bound),
            )

    if interactive:
        bound = _fill_required_options(command, bound, prompt=prompt)
        record(
            "arguments.interactive",
            "filled interactive command arguments",
            project=project.name,
            command=list(command.path),
            argv=list(bound),
        )

    decoded = _decode_structured_argv(command, bound)
    record(
        "arguments.decode",
        "decoded structured command arguments",
        project=project.name,
        command=list(command.path),
        before=list(bound),
        after=list(decoded),
    )
    return decoded


__all__ = ["bind_command_arguments"]
