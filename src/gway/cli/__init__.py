from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version as distribution_version

from .. import __version__
from ..dispatcher import Dispatcher
from ..expression import normalize_managed_args
from ..install import Installer
from ..operations.install import install_project
from ..operations.project import (
    managed_status as _shared_managed_status,
    runtime_component_record as _shared_runtime_component_record,
    upgrade_status as _shared_upgrade_status,
)
from ..operations.service import (
    install_project_service as _shared_install_project_service,
    run_service as _shared_run_service,
)
from ..operations.upgrade import run_upgrade as _shared_run_upgrade
from ..project import Project
from ..registry import Registry, RegistryError
from ..runtime import GwayRuntime
from ..service import ServiceManager
from ..shell import (
    install_shell,
    integration_snippet,
    launch_shell,
    shell_status,
    uninstall_shell,
)
from ..solve import solve_values
from ..stage import StageKind, StageSyntaxError, parse_stages
from ..upgrade import UpgradeResult, Upgrader
from .errors import (
    _can_suggest_sudo,
    _extract_global_flags,
    _handle_cli_exception,
    _known_cli_error,
    _managed_result_name,
    _permission_failure,
    _prompt_required_value,
    _report_error,
)
from .handlers import handle_core_command
from .help import _print_project_help
from .render import _render_result, _render_upgrade_record

CORE_COMMANDS = frozenset(
    {"list", "info", "path", "register", "install", "upgrade", "service", "shell", "solve", "recipe"}
)
RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gway",
        description="Manage and dispatch GWAY/Arthexis projects.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render command results as JSON instead of human-readable output.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt for missing required managed-command values.",
    )

    subparsers = parser.add_subparsers(dest="command")

    list_projects = subparsers.add_parser("list", help="List registered projects.")
    list_projects.add_argument(
        "--detail",
        action="store_true",
        help="Show detailed metadata for each registered project.",
    )

    info = subparsers.add_parser("info", help="Show project metadata.")
    info.add_argument("project")

    path = subparsers.add_parser("path", help="Print a project's local path.")
    path.add_argument("project")

    solve = subparsers.add_parser(
        "solve",
        help="Resolve a Sigil template using GWAY's base context.",
    )
    solve.add_argument("value", nargs="+", help="Sigil template to resolve.")

    recipe = subparsers.add_parser(
        "recipe",
        help="Execute a .rx recipe file.",
    )
    recipe.add_argument("path", help="Path to the .rx recipe file.")

    register = subparsers.add_parser(
        "register",
        help="Register a local project containing gway.toml.",
    )
    register.add_argument("path")

    install = subparsers.add_parser(
        "install",
        help="Install a trusted GitHub project or built-in runtime component.",
    )
    install.add_argument("project")
    install.add_argument(
        "--service",
        action="store_true",
        help="Install manifest-defined system services after installing the project.",
    )
    install.add_argument(
        "--adopt",
        action="store_true",
        help="Adopt state from an existing unmanaged project installation.",
    )
    install.add_argument(
        "--from",
        dest="adopt_from",
        metavar="PATH",
        help="Explicit unmanaged source checkout to inspect for --adopt.",
    )
    install.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and plan --adopt without creating managed resources.",
    )

    upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade GWAY itself and/or trusted managed projects.",
    )
    upgrade.add_argument("projects", nargs="*")
    upgrade.add_argument(
        "--all",
        action="store_true",
        help="Upgrade all trusted managed projects.",
    )
    upgrade.add_argument(
        "--self",
        dest="upgrade_self",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include or exclude GWAY itself from the upgrade.",
    )
    force_mode = upgrade.add_mutually_exclusive_group()
    force_mode.add_argument(
        "--force",
        action="store_true",
        help=(
            "Discard local managed-checkout changes and reset projects to their trusted "
            "upstream branches before upgrading."
        ),
    )
    force_mode.add_argument(
        "--try-force",
        action="store_true",
        help=(
            "Try a normal managed-project upgrade first, then retry once with --force "
            "only if the repository upgrade fails."
        ),
    )
    upgrade.add_argument(
        "--reload",
        action="store_true",
        help="Refresh managed projects even when the tracked commit is unchanged.",
    )
    upgrade.add_argument(
        "--detail",
        action="store_true",
        help="Show detailed upgrade metadata instead of one line per package.",
    )

    service = subparsers.add_parser(
        "service",
        help="Manage a project's system service declared in gway.toml.",
    )
    service.add_argument(
        "action",
        choices=("install", "uninstall", "start", "stop", "restart", "status"),
    )
    service.add_argument(
        "project",
        nargs="?",
        help="Registered project name or alias.",
    )
    service.add_argument(
        "--project",
        dest="project_option",
        help="Registered project name or alias (legacy option spelling).",
    )
    service.add_argument(
        "--user",
        help="Service account override for installation.",
    )
    service.add_argument(
        "--no-enable",
        dest="enable",
        action="store_false",
        default=True,
        help="Install without enabling the service at boot.",
    )
    service.add_argument(
        "--no-start",
        dest="start",
        action="store_false",
        default=True,
        help="Install without starting/restarting the service.",
    )

    shell = subparsers.add_parser(
        "shell",
        help="Start or install the GWAY '-' and '%%' shell shorthands.",
    )
    shell.add_argument(
        "action",
        nargs="?",
        choices=("install", "uninstall", "status", "print"),
        help="Manage persistent shell integration; omit to start an ephemeral shell.",
    )
    shell.add_argument(
        "--shell",
        dest="shell_name",
        choices=("bash", "zsh"),
        help="Shell to use instead of auto-detecting $SHELL.",
    )

    return parser


def _project_record(project: Project) -> dict[str, object]:
    record: dict[str, object] = {
        "name": project.name,
        "path": project.path,
        "adapter": project.adapter_type,
    }
    if project.aliases:
        record["aliases"] = list(project.aliases)
    if project.repository:
        record["repository"] = project.repository
    if project.revision:
        record["revision"] = project.revision
    if project.service_config is not None:
        record["service"] = project.service_config
    return record


def _runtime_component_record(name: str) -> dict[str, object] | None:
    return _shared_runtime_component_record(name, version_resolver=distribution_version)


def _managed_status(status: str, project: Project) -> dict[str, object]:
    return _shared_managed_status(status, project)


def _upgrade_status(status: str, result: UpgradeResult) -> dict[str, object]:
    return _shared_upgrade_status(status, result)


def _install_project_service(project: Project) -> dict[str, object]:
    return _shared_install_project_service(project, manager_factory=ServiceManager)


def _run_upgrade(
    namespace: argparse.Namespace,
    registry: Registry,
    *,
    json_output: bool,
    arguments: Sequence[str] = (),
) -> object:
    on_completed = None
    if not json_output:
        on_completed = lambda record: _render_upgrade_record(record, detail=namespace.detail)
    result = _shared_run_upgrade(
        registry,
        projects=namespace.projects,
        all_projects=namespace.all,
        upgrade_self=namespace.upgrade_self,
        force=namespace.force,
        try_force=namespace.try_force,
        reload=namespace.reload,
        arguments=arguments,
        upgrader_factory=Upgrader,
        on_completed=on_completed,
    )
    return result if json_output else None


def _run_service(namespace: argparse.Namespace, registry: Registry) -> object:
    return _shared_run_service(
        registry,
        action=namespace.action,
        project_name=namespace.project,
        user=namespace.user,
        enable=namespace.enable,
        start=namespace.start,
        manager_factory=ServiceManager,
    )


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    parser = build_parser()
    original_args = list(sys.argv[1:] if argv is None else argv)
    args, json_output, interactive = _extract_global_flags(original_args)
    if not args:
        parser.print_help()
        return 0

    active_dispatcher = dispatcher or Dispatcher()

    try:
        stages = parse_stages(args)
    except StageSyntaxError as exc:
        return _handle_cli_exception(exc, original_args)
    if len(stages) == 1 and stages[0].kind is StageKind.SOLVE:
        try:
            result = solve_values(
                stages[0].raw_tokens,
                interactive=interactive,
                prompt=_prompt_required_value,
            )
            _render_result(result, json_output=json_output, result_name="solve")
        except Exception as exc:
            return _handle_cli_exception(exc, original_args)
        return 0

    if args[0] not in CORE_COMMANDS and not args[0].startswith("-"):
        try:
            project_name, project_args = normalize_managed_args(args)
            if project_args in (["--help"], ["-h"]):
                _print_project_help(active_dispatcher, project_name)
                return 0
            result = active_dispatcher.run(
                project_name,
                project_args,
                interactive=interactive,
            )
            _render_result(
                result,
                json_output=json_output,
                result_name=_managed_result_name(project_name, project_args),
            )
        except Exception as exc:
            return _handle_cli_exception(exc, original_args)
        return 0

    registry = active_dispatcher.registry
    namespace, passthrough = parser.parse_known_args(args)
    if passthrough and namespace.command not in {"install", "upgrade", "recipe"}:
        parser.error(f"unrecognized arguments: {' '.join(passthrough)}")
    if namespace.command == "service":
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
                namespace.project = _prompt_required_value("project")
            else:
                parser.error("the following arguments are required: project")

    try:
        outcome = handle_core_command(
            namespace,
            passthrough,
            dispatcher=active_dispatcher,
            registry=registry,
            interactive=interactive,
            json_output=json_output,
            prompt=_prompt_required_value,
            project_record=_project_record,
            runtime_component_record=_runtime_component_record,
            managed_status=_managed_status,
            run_upgrade=_run_upgrade,
            run_service=_run_service,
            solve=solve_values,
            runtime_factory=GwayRuntime,
            installer_factory=Installer,
            install_project_op=install_project,
            service_manager_factory=ServiceManager,
            install_shell_fn=install_shell,
            uninstall_shell_fn=uninstall_shell,
            shell_status_fn=shell_status,
            launch_shell_fn=launch_shell,
            integration_snippet_fn=integration_snippet,
        )
        if outcome.show_help:
            parser.print_help()
            return 0
        if outcome.exit_code is not None:
            return outcome.exit_code
        if outcome.render:
            _render_result(
                outcome.value,
                json_output=json_output,
                result_name=namespace.command,
            )
    except Exception as exc:
        return _handle_cli_exception(exc, original_args)

    return 0
