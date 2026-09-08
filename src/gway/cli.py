from __future__ import annotations

import argparse
import errno
import json
import math
import os
import shlex
import shutil
import sys
import textwrap
from collections.abc import Mapping, Sequence
from importlib.metadata import version as distribution_version

from . import __version__
from .adapters import AdapterError
from .config import ConfigError
from .dispatcher import Dispatcher, DispatchError
from .expression import ExpressionError, normalize_managed_args
from .install import Installer
from .project import ManifestError, Project
from .registry import Registry, RegistryError
from .repository import RepositoryError
from .runner import RunnerError
from .service import ServiceError, ServiceManager
from .upgrade import UpgradeError, Upgrader

CORE_COMMANDS = frozenset({"list", "info", "path", "register", "install", "upgrade", "service"})
RUNTIME_COMPONENTS = {"sigils": "gway-sigils"}
_PERMISSION_ERRNOS = frozenset({errno.EACCES, errno.EPERM})
_RESET = "\033[0m"
_KEY = "\033[36m"
_STRING = "\033[32m"
_NUMBER = "\033[33m"
_BOOL = "\033[35m"
_NULL = "\033[2m"


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
        help="Prompt for missing required managed-command option values.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List registered projects.")

    info = subparsers.add_parser("info", help="Show project metadata.")
    info.add_argument("project")

    path = subparsers.add_parser("path", help="Print a project's local path.")
    path.add_argument("project")

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

    upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade GWAY itself and/or trusted managed projects.",
    )
    upgrade.add_argument("project", nargs="?")
    upgrade.add_argument(
        "--all",
        action="store_true",
        help="Upgrade all trusted managed projects.",
    )
    upgrade.add_argument(
        "--self",
        dest="upgrade_self",
        action="store_true",
        help="Upgrade GWAY itself in the current installation environment.",
    )
    upgrade.add_argument(
        "--force",
        action="store_true",
        help=(
            "Discard local managed-checkout changes and reset projects to their trusted "
            "upstream branches before upgrading."
        ),
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


def _print_project_help(dispatcher: Dispatcher, project_name: str) -> None:
    project = dispatcher.registry.require(project_name)
    commands = dispatcher.commands(project_name)
    print(f"usage: gway {project.name} <command> [arguments]")
    print()
    print("commands:")

    rows = [(" ".join(command.path), command.summary) for command in commands]
    if not rows:
        return

    terminal_width = max(1, shutil.get_terminal_size(fallback=(100, 24)).columns)
    left_indent = 2 if terminal_width >= 4 else 0
    gap = 2
    name_width = max(len(name) for name, _ in rows)
    description_column = left_indent + name_width + gap
    description_width = terminal_width - description_column

    for name, summary in rows:
        if not summary:
            for line in textwrap.wrap(
                name,
                width=max(1, terminal_width - left_indent),
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]:
                print(f"{' ' * left_indent}{line}")
            continue

        if description_width < 20:
            available = max(1, terminal_width - left_indent)
            for line in textwrap.wrap(
                name,
                width=available,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]:
                print(f"{' ' * left_indent}{line}")
            detail_indent = min(left_indent * 2, max(0, terminal_width - 1))
            detail_width = max(1, terminal_width - detail_indent)
            for line in textwrap.wrap(summary, width=detail_width) or [""]:
                print(f"{' ' * detail_indent}{line}")
            continue

        wrapped = textwrap.wrap(summary, width=description_width) or [""]
        print(f"{' ' * left_indent}{name:<{name_width}}{' ' * gap}{wrapped[0]}")
        continuation = " " * description_column
        for line in wrapped[1:]:
            print(f"{continuation}{line}")


def _paint(text: str, code: str, *, color: bool) -> str:
    if not color:
        return text
    return f"{code}{text}{_RESET}"


def _scalar_text(value: object, *, color: bool) -> str:
    if value is None:
        return _paint("null", _NULL, color=color)
    if isinstance(value, bool):
        return _paint("true" if value else "false", _BOOL, color=color)
    if isinstance(value, (int, float)):
        return _paint(str(value), _NUMBER, color=color)
    if isinstance(value, str):
        return _paint(value, _STRING, color=color)
    return str(value)


def _is_nested(value: object) -> bool:
    return isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _empty_collection_text(value: object) -> str | None:
    if isinstance(value, Mapping) and not value:
        return "{}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and not value:
        return "[]"
    return None


def _pretty_lines(value: object, *, indent: int = 0, color: bool = False) -> list[str]:
    prefix = "  " * indent
    empty = _empty_collection_text(value)
    if empty is not None:
        return [f"{prefix}{empty}"]

    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            label = _paint(str(key), _KEY, color=color)
            item_empty = _empty_collection_text(item)
            if item_empty is not None:
                lines.append(f"{prefix}{label}: {item_empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}{label}:")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}{label}: {_scalar_text(item, color=color)}")
        return lines

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        lines = []
        for item in value:
            item_empty = _empty_collection_text(item)
            if item_empty is not None:
                lines.append(f"{prefix}- {item_empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}-")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}- {_scalar_text(item, color=color)}")
        return lines

    return [f"{prefix}{_scalar_text(value, color=color)}"]


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def _color_enabled() -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _render_result(
    result: object,
    *,
    json_output: bool = False,
    color: bool | None = None,
) -> None:
    if result is None:
        return
    if json_output:
        print(json.dumps(_json_safe(result), indent=2, default=str, allow_nan=False))
        return

    use_color = _color_enabled() if color is None else color
    for line in _pretty_lines(result, color=use_color):
        print(line)


def _extract_global_flags(args: list[str]) -> tuple[list[str], bool, bool]:
    json_output = "--json" in args
    interactive = "-i" in args or "--interactive" in args
    reserved = {"--json", "-i", "--interactive"}
    return [arg for arg in args if arg not in reserved], json_output, interactive


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


def _run_upgrade(
    namespace: argparse.Namespace,
    registry: Registry,
    *,
    json_output: bool,
) -> object:
    if namespace.project and (namespace.all or namespace.upgrade_self):
        raise UpgradeError("PROJECT cannot be combined with --all or --self")

    upgrader = Upgrader(registry)
    if namespace.project:
        project = upgrader.project(namespace.project, force=namespace.force)
        return _managed_status("upgraded", project)

    results: list[dict[str, object]] = []

    def completed(record: dict[str, object]) -> None:
        if json_output:
            results.append(record)
        else:
            _render_result(record)

    bare = not namespace.all and not namespace.upgrade_self
    if bare or namespace.upgrade_self:
        upgrader.upgrade_self()
        completed(
            {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }
        )

    if bare or namespace.all:
        for project in upgrader.all_projects(force=namespace.force):
            completed(_managed_status("upgraded", project))

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
            RegistryError,
            RepositoryError,
            RunnerError,
            ServiceError,
            UpgradeError,
            OSError,
        ),
    )


def _handle_cli_exception(exc: Exception, args: Sequence[str]) -> int:
    if not _known_cli_error(exc) and _permission_failure(exc) is None:
        raise exc
    _report_error(exc, args)
    return 2


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    parser = build_parser()
    original_args = list(sys.argv[1:] if argv is None else argv)
    args, json_output, interactive = _extract_global_flags(original_args)
    if not args:
        parser.print_help()
        return 0

    active_dispatcher = dispatcher or Dispatcher()
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
            _render_result(result, json_output=json_output)
        except Exception as exc:
            return _handle_cli_exception(exc, original_args)
        return 0

    namespace = parser.parse_args(args)
    if namespace.command == "service":
        if namespace.project and namespace.project_option and namespace.project != namespace.project_option:
            parser.error("PROJECT and --project must name the same project")
        namespace.project = namespace.project or namespace.project_option
        if namespace.project is None:
            if interactive:
                namespace.project = _prompt_required_value("project")
            else:
                parser.error("the following arguments are required: project")

    registry = active_dispatcher.registry

    try:
        result: object = None
        if namespace.command == "list":
            result = [_project_record(project) for project in registry.list()]
        elif namespace.command == "info":
            result = _project_record(registry.require(namespace.project))
        elif namespace.command == "path":
            result = registry.require(namespace.project).path
        elif namespace.command == "register":
            project = registry.register_path(namespace.path)
            result = _managed_status("registered", project)
        elif namespace.command == "install":
            result = _runtime_component_record(namespace.project)
            if result is None:
                project = Installer(registry).install(namespace.project)
                result = _managed_status("installed", project)
        elif namespace.command == "upgrade":
            result = _run_upgrade(namespace, registry, json_output=json_output)
        elif namespace.command == "service":
            result = _run_service(namespace, registry)
        else:
            parser.print_help()
            return 0
        _render_result(result, json_output=json_output)
    except Exception as exc:
        return _handle_cli_exception(exc, original_args)

    return 0
