from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ..dispatcher import Dispatcher
from ..expression import normalize_managed_args
from ..registry import RegistryError
from ..stage import StageKind, StageSyntaxError, parse_stages
from .errors import extract_global_flags, managed_result_name
from .handlers import HandlerResult, handle_core_command
from .parser import CORE_COMMANDS, build_parser


@dataclass(frozen=True)
class CliDependencies:
    solve_values: Callable[..., object]
    prompt_required_value: Callable[[str], str]
    render_result: Callable[..., None]
    handle_cli_exception: Callable[[Exception, Sequence[str]], int]
    print_project_help: Callable[[Dispatcher, str], None]
    project_record: Callable[[Any], dict[str, object]]
    runtime_component_record: Callable[[str], dict[str, object] | None]
    managed_status: Callable[[str, Any], dict[str, object]]
    run_upgrade: Callable[..., object]
    run_service: Callable[..., object]
    runtime_factory: Callable[..., Any]
    installer_factory: Callable[..., Any]
    install_project_op: Callable[..., dict[str, object]]
    service_manager_factory: Callable[..., Any]
    install_shell: Callable[..., object]
    uninstall_shell: Callable[..., object]
    shell_status: Callable[..., object]
    launch_shell: Callable[..., int]
    integration_snippet: Callable[..., str]


def _normalize_service_project(
    namespace: Any,
    registry: Any,
    *,
    parser: Any,
    interactive: bool,
    prompt_required_value: Callable[[str], str],
) -> None:
    if namespace.project and namespace.project_option:
        try:
            positional_name = registry.require(namespace.project).name
            option_name = registry.require(namespace.project_option).name
        except RegistryError:
            same_project = namespace.project == namespace.project_option
        else:
            same_project = positional_name == option_name
        if not same_project:
            parser.error("PROJECT and --project must name the same project")
    namespace.project = namespace.project or namespace.project_option
    if namespace.project is None:
        if interactive:
            namespace.project = prompt_required_value("project")
        else:
            parser.error("the following arguments are required: project")


def run_main(
    argv: Sequence[str] | None = None,
    *,
    dispatcher: Dispatcher | None = None,
    dependencies: CliDependencies,
) -> int:
    """Run the command-line interface using explicitly supplied adapter dependencies."""
    parser = build_parser()
    original_args = list(sys.argv[1:] if argv is None else argv)
    args, json_output, interactive = extract_global_flags(original_args)
    if not args:
        parser.print_help()
        return 0

    active_dispatcher = dispatcher or Dispatcher()

    try:
        stages = parse_stages(args)
    except StageSyntaxError as exc:
        return dependencies.handle_cli_exception(exc, original_args)
    if len(stages) == 1 and stages[0].kind is StageKind.SOLVE:
        try:
            result = dependencies.solve_values(
                stages[0].raw_tokens,
                interactive=interactive,
                prompt=dependencies.prompt_required_value,
            )
            dependencies.render_result(result, json_output=json_output, result_name="solve")
        except Exception as exc:
            return dependencies.handle_cli_exception(exc, original_args)
        return 0

    if args[0] not in CORE_COMMANDS and not args[0].startswith("-"):
        try:
            project_name, project_args = normalize_managed_args(args)
            if project_args in (["--help"], ["-h"]):
                dependencies.print_project_help(active_dispatcher, project_name)
                return 0
            result = active_dispatcher.run(
                project_name,
                project_args,
                interactive=interactive,
            )
            dependencies.render_result(
                result,
                json_output=json_output,
                result_name=managed_result_name(project_name, project_args),
            )
        except Exception as exc:
            return dependencies.handle_cli_exception(exc, original_args)
        return 0

    registry = active_dispatcher.registry
    namespace, passthrough = parser.parse_known_args(args)
    if passthrough and namespace.command not in {"install", "upgrade", "recipe"}:
        parser.error(f"unrecognized arguments: {' '.join(passthrough)}")
    if namespace.command == "service":
        _normalize_service_project(
            namespace,
            registry,
            parser=parser,
            interactive=interactive,
            prompt_required_value=dependencies.prompt_required_value,
        )

    try:
        outcome: HandlerResult = handle_core_command(
            namespace,
            passthrough,
            dispatcher=active_dispatcher,
            registry=registry,
            interactive=interactive,
            json_output=json_output,
            prompt=dependencies.prompt_required_value,
            project_record=dependencies.project_record,
            runtime_component_record=dependencies.runtime_component_record,
            managed_status=dependencies.managed_status,
            run_upgrade=dependencies.run_upgrade,
            run_service=dependencies.run_service,
            solve=dependencies.solve_values,
            runtime_factory=dependencies.runtime_factory,
            installer_factory=dependencies.installer_factory,
            install_project_op=dependencies.install_project_op,
            service_manager_factory=dependencies.service_manager_factory,
            install_shell_fn=dependencies.install_shell,
            uninstall_shell_fn=dependencies.uninstall_shell,
            shell_status_fn=dependencies.shell_status,
            launch_shell_fn=dependencies.launch_shell,
            integration_snippet_fn=dependencies.integration_snippet,
        )
        if outcome.show_help:
            parser.print_help()
            return 0
        if outcome.exit_code is not None:
            return outcome.exit_code
        if outcome.render:
            dependencies.render_result(
                outcome.value,
                json_output=json_output,
                result_name=namespace.command,
            )
    except Exception as exc:
        return dependencies.handle_cli_exception(exc, original_args)

    return 0


__all__ = ["CliDependencies", "run_main"]
