from __future__ import annotations

import argparse
import errno
import os
import shlex
import shutil
import sys
from collections.abc import Sequence
from importlib.metadata import version as distribution_version

from .. import __version__
from ..adapters import AdapterError
from ..config import ConfigError
from ..dispatcher import Dispatcher, DispatchError
from ..expression import ExpressionError, normalize_managed_args
from ..install import Installer
from ..project import ManifestError, Project
from ..recipe import RecipeError
from ..registry import Registry, RegistryError
from ..repository import RepositoryError
from ..runner import RunnerError
from ..runtime import GwayRuntime
from ..service import ServiceError, ServiceManager
from ..shell import (
    ShellError,
    install_shell,
    integration_snippet,
    launch_shell,
    shell_status,
    uninstall_shell,
)
from ..solve import solve_values
from ..stage import StageKind, StageSyntaxError, parse_stages
from ..upgrade import UpgradeError, UpgradeResult, Upgrader
from .help import _print_project_help
from .render import _render_result, _render_upgrade_record

CORE_COMMANDS = frozenset(
    {"list", "info", "path", "register", "install", "upgrade", "service", "shell", "solve", "recipe"}
)
RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}
_PERMISSION_ERRNOS = frozenset({errno.EACCES, errno.EPERM})


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


def _extract_global_flags(args: list[str]) -> tuple[list[str], bool, bool]:
    filtered: list[str] = []
    json_output = False
    interactive = False
    literal = False

    for arg in args:
        if literal:
            filtered.append(arg)
            continue
        if arg == "--":
            literal = True
            filtered.append(arg)
            continue
        if arg == "--json":
            json_output = True
            continue
        if arg in {"-i", "--interactive"}:
            interactive = True
            continue
        filtered.append(arg)

    return filtered, json_output, interactive


def _prompt_required_value(name: str) -> str:
    while True:
        print(f"{name}: ", end="", file=sys.stderr, flush=True)
        value = input()
        if value:
            return value
        print("A value is required.", file=sys.stderr)


def _permission_failure(exc: BaseException) -> OSError | None:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, PermissionError):
            return current
        if isinstance(current, OSError) and current.errno in _PERMISSION_ERRNOS:
            return current
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return None


def _can_suggest_sudo() -> bool:
    if os.name != "posix" or shutil.which("sudo") is None:
        return False
    geteuid = getattr(os, "geteuid", None)
    return not callable(geteuid) or geteuid() != 0


def _report_error(exc: BaseException, args: Sequence[str]) -> None:
    print(f"gway: {exc}", file=sys.stderr)
    if _permission_failure(exc) is not None and _can_suggest_sudo():
        command = shlex.join(["gway", *args])
        print(f"hint: try running with sudo: sudo {command}", file=sys.stderr)


def _runtime_component_record(name: str) -> dict[str, object] | None:
    distribution = RUNTIME_COMPONENTS.get(name)
    if distribution is None:
        return None
    return {
        "status": "installed",
        "name": name,
        "distribution": distribution,
        "version": distribution_version(distribution),
    }


def _managed_status(status: str, project: Project) -> dict[str, object]:
    record: dict[str, object] = {
        "status": status,
        "name": project.name,
        "path": project.path,
    }
    if project.repository:
        record["repository"] = project.repository
    if project.revision:
        record["revision"] = project.revision
    return record


def _upgrade_status(status: str, result: UpgradeResult) -> dict[str, object]:
    record = _managed_status(status, result.project)
    record["force_used"] = bool(getattr(result, "force_used", False))
    force_error_type = getattr(result, "force_error_type", None)
    force_error = getattr(result, "force_error", None)
    dirty_files = getattr(result, "dirty_files", ())
    if force_error_type is not None:
        record["force_error_type"] = force_error_type
    if force_error is not None:
        record["force_error"] = force_error
    if dirty_files:
        record["dirty_files"] = [
            {
                "status": entry.status,
                "path": entry.path,
                **(
                    {"original_path": entry.original_path}
                    if entry.original_path is not None
                    else {}
                ),
            }
            for entry in dirty_files
        ]
    return record


def _install_project_service(project: Project) -> dict[str, object]:
    try:
        manager = ServiceManager(project)
    except ServiceError as exc:
        if "does not declare [service] or [services]" not in str(exc):
            raise
        return {
            "status": "not-provided",
            "message": f"{project.name} does not provide a service",
        }
    unit = manager.install()
    return {"status": "installed", "unit": unit}


def _run_upgrade(
    namespace: argparse.Namespace,
    registry: Registry,
    *,
    json_output: bool,
    arguments: Sequence[str] = (),
) -> object:
    targets = list(dict.fromkeys(namespace.projects))
    if targets and (namespace.all or namespace.upgrade_self is not None):
        raise UpgradeError("PROJECTS cannot be combined with --all, --self, or --no-self")

    include_self_target = "gway" in targets
    managed_targets = [target for target in targets if target != "gway"]
    if arguments and len(managed_targets) != 1:
        raise UpgradeError("installer arguments require exactly one managed PROJECT")

    upgrader = Upgrader(registry)
    results: list[dict[str, object]] = []

    def completed(record: dict[str, object]) -> None:
        if json_output:
            results.append(record)
        else:
            _render_upgrade_record(record, detail=namespace.detail)

    if targets:
        if include_self_target:
            upgrader.upgrade_self()
            completed(
                {
                    "status": "upgraded",
                    "name": "gway",
                    "repository": "arthexis/gway",
                    "revision": "main",
                }
            )

        for target in managed_targets:
            upgrade_kwargs = {"try_force": True} if namespace.try_force else {}
            result = upgrader.project_result(
                target,
                force=namespace.force,
                reload=namespace.reload,
                arguments=arguments if len(managed_targets) == 1 else (),
                **upgrade_kwargs,
            )
            completed(_upgrade_status("upgraded" if result.changed else "skipped", result))

        if json_output and len(managed_targets) == 1 and not include_self_target:
            return results[0]
        return results if json_output else None

    default_mode = not namespace.all and namespace.upgrade_self is None
    include_self = namespace.upgrade_self is True or (
        namespace.upgrade_self is None and (default_mode or namespace.all)
    )
    include_projects = namespace.all or default_mode or namespace.upgrade_self is False

    if include_self:
        upgrader.upgrade_self()
        completed(
            {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }
        )

    if include_projects:
        upgrade_kwargs = {"try_force": True} if namespace.try_force else {}
        for result in upgrader.all_project_results(
            force=namespace.force,
            reload=namespace.reload,
            **upgrade_kwargs,
        ):
            status = "upgraded" if result.changed else "skipped"
            completed(_upgrade_status(status, result))

    return results if json_output else None


def _run_service(namespace: argparse.Namespace, registry: Registry) -> object:
    project = registry.require(namespace.project)
    manager = ServiceManager(project)
    if namespace.action == "install":
        unit = manager.install(user=namespace.user, enable=namespace.enable, start=namespace.start)
        return {"status": "installed", "project": project.name, "unit": unit}
    if namespace.action == "uninstall":
        removed = manager.uninstall()
        return {"status": "uninstalled", "project": project.name, "removed": removed}
    if namespace.action == "start":
        manager.start()
        return {"status": "started", "project": project.name, "unit": manager.unit_name}
    if namespace.action == "stop":
        manager.stop()
        return {"status": "stopped", "project": project.name, "unit": manager.unit_name}
    if namespace.action == "restart":
        manager.restart()
        return {"status": "restarted", "project": project.name, "unit": manager.unit_name}
    return manager.status()


def _known_cli_error(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            AdapterError,
            ConfigError,
            DispatchError,
            ExpressionError,
            ManifestError,
            RecipeError,
            RegistryError,
            RepositoryError,
            RunnerError,
            ServiceError,
            ShellError,
            StageSyntaxError,
            UpgradeError,
            OSError,
        ),
    )


def _handle_cli_exception(exc: Exception, args: Sequence[str]) -> int:
    if not _known_cli_error(exc) and _permission_failure(exc) is None:
        raise exc
    _report_error(exc, args)
    return 2


def _managed_result_name(project_name: str, project_args: Sequence[str]) -> str:
    if project_args:
        command_name = project_args[0]
        if command_name and not command_name.startswith("-"):
            return command_name.replace("-", "_")
    return project_name.replace("-", "_")


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
        result: object = None
        if namespace.command == "list":
            projects = registry.list()
            if namespace.detail:
                result = [_project_record(project) for project in projects]
            else:
                result = [project.name for project in projects]
        elif namespace.command == "info":
            result = _project_record(registry.require(namespace.project))
        elif namespace.command == "path":
            result = registry.require(namespace.project).path
        elif namespace.command == "solve":
            result = solve_values(
                namespace.value,
                interactive=interactive,
                prompt=_prompt_required_value,
            )
        elif namespace.command == "recipe":
            recipe_tokens = ["recipe"]
            if namespace.path.startswith("-"):
                recipe_tokens.append("--")
            recipe_tokens.extend([namespace.path, *passthrough])
            result = GwayRuntime(active_dispatcher).execute(
                recipe_tokens,
                interactive=interactive,
                prompt=_prompt_required_value if interactive else None,
            )
        elif namespace.command == "register":
            project = registry.register_path(namespace.path)
            result = _managed_status("registered", project)
        elif namespace.command == "install":
            if namespace.adopt_from and not namespace.adopt:
                raise RunnerError("--from requires --adopt")
            if namespace.dry_run and not namespace.adopt:
                raise RunnerError("--dry-run requires --adopt")
            if namespace.adopt and not namespace.adopt_from:
                raise RunnerError("--adopt requires --from PATH")
            if namespace.adopt and not namespace.dry_run:
                raise RunnerError(
                    "managed adoption execution is not available yet; rerun with --dry-run"
                )
            if namespace.adopt and namespace.service:
                raise RunnerError("--service cannot be combined with --adopt --dry-run")

            result = _runtime_component_record(namespace.project)
            if result is not None and namespace.adopt:
                raise RunnerError("built-in runtime components cannot be adopted")
            if result is not None and passthrough:
                raise RunnerError(
                    "built-in runtime component install does not accept project arguments"
                )
            if result is not None and namespace.service:
                result["service"] = {
                    "status": "not-provided",
                    "message": f"{namespace.project} does not provide a service",
                }
            if result is None:
                installer = Installer(registry)
                if namespace.adopt:
                    lifecycle_arguments = (
                        "--adopt",
                        "--from",
                        namespace.adopt_from,
                        "--dry-run",
                        *passthrough,
                    )
                    preview = installer.preview_adoption(
                        namespace.project,
                        namespace.adopt_from,
                        arguments=lifecycle_arguments,
                    )
                    result = {
                        "status": "preflight",
                        "name": preview.name,
                        "source": preview.source,
                        "target": preview.target,
                        "revision": preview.revision,
                        "adopt": True,
                        "dry_run": True,
                    }
                else:
                    if passthrough:
                        project = installer.install(namespace.project, arguments=passthrough)
                    else:
                        project = installer.install(namespace.project)
                    result = _managed_status("installed", project)
                    if namespace.service:
                        result["service"] = _install_project_service(project)
        elif namespace.command == "upgrade":
            result = _run_upgrade(
                namespace,
                registry,
                json_output=json_output,
                arguments=passthrough,
            )
        elif namespace.command == "service":
            result = _run_service(namespace, registry)
        elif namespace.command == "shell":
            if namespace.action is None:
                return launch_shell(namespace.shell_name)
            if namespace.action == "print":
                print(integration_snippet(namespace.shell_name), end="")
                return 0
            if namespace.action == "install":
                result = install_shell(namespace.shell_name)
            elif namespace.action == "uninstall":
                result = uninstall_shell(namespace.shell_name)
            else:
                result = shell_status(namespace.shell_name)
        else:
            parser.print_help()
            return 0
        _render_result(
            result,
            json_output=json_output,
            result_name=namespace.command,
        )
    except Exception as exc:
        return _handle_cli_exception(exc, original_args)

    return 0
