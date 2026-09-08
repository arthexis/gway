from __future__ import annotations

import argparse
import errno
import json
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
from .install import Installer
from .project import ManifestError, Project
from .registry import Registry, RegistryError
from .repository import RepositoryError
from .runner import RunnerError
from .upgrade import UpgradeError, Upgrader

CORE_COMMANDS = frozenset({"list", "info", "path", "register", "install", "upgrade"})
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

    terminal_width = max(40, shutil.get_terminal_size(fallback=(100, 24)).columns)
    name_width = max(len(name) for name, _ in rows)
    left_indent = 2
    gap = 2
    description_column = left_indent + name_width + gap
    description_width = terminal_width - description_column

    for name, summary in rows:
        if not summary:
            print(f"{' ' * left_indent}{name}")
            continue

        if description_width < 20:
            print(f"{' ' * left_indent}{name}")
            wrapped = textwrap.wrap(summary, width=max(20, terminal_width - left_indent * 2))
            for line in wrapped:
                print(f"{' ' * (left_indent * 2)}{line}")
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
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and not value
    ):
        return "[]"
    return None


def _pretty_lines(value: object, *, indent: int = 0, color: bool = False) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            label = _paint(str(key), _KEY, color=color)
            empty = _empty_collection_text(item)
            if empty is not None:
                lines.append(f"{prefix}{label}: {empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}{label}:")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}{label}: {_scalar_text(item, color=color)}")
        return lines

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        lines = []
        for item in value:
            empty = _empty_collection_text(item)
            if empty is not None:
                lines.append(f"{prefix}- {empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}-")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}- {_scalar_text(item, color=color)}")
        return lines

    return [f"{prefix}{_scalar_text(value, color=color)}"]


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
        print(json.dumps(result, indent=2, default=str))
        return

    use_color = _color_enabled() if color is None else color
    for line in _pretty_lines(result, color=use_color):
        print(line)


def _extract_global_flags(args: list[str]) -> tuple[list[str], bool, bool]:
    json_output = "--json" in args
    interactive = "-i" in args or "--interactive" in args
    reserved = {"--json", "-i", "--interactive"}
    return [arg for arg in args if arg not in reserved], json_output, interactive


def _permission_failure(exc: BaseException) -> OSError | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, PermissionError):
            return current
        if isinstance(current, OSError) and current.errno in _PERMISSION_ERRNOS:
            return current
        current = current.__cause__ or current.__context__
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


def _run_upgrade(namespace: argparse.Namespace, registry: Registry) -> object:
    if namespace.project and (namespace.all or namespace.upgrade_self):
        raise UpgradeError("PROJECT cannot be combined with --all or --self")

    upgrader = Upgrader(registry)
    if namespace.project:
        project = upgrader.project(namespace.project, force=namespace.force)
        return _managed_status("upgraded", project)

    results: list[dict[str, object]] = []
    bare = not namespace.all and not namespace.upgrade_self
    if bare or namespace.upgrade_self:
        upgrader.upgrade_self()
        results.append(
            {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }
        )

    if bare or namespace.all:
        for project in upgrader.all_projects(force=namespace.force):
            results.append(_managed_status("upgraded", project))
    return results


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    parser = build_parser()
    original_args = list(sys.argv[1:] if argv is None else argv)
    args, json_output, interactive = _extract_global_flags(original_args)
    if not args:
        parser.print_help()
        return 0

    active_dispatcher = dispatcher or Dispatcher()
    if args[0] not in CORE_COMMANDS and not args[0].startswith("-"):
        project_args = list(args[1:])
        try:
            if project_args in (["--help"], ["-h"]):
                _print_project_help(active_dispatcher, args[0])
                return 0
            result = active_dispatcher.run(args[0], project_args, interactive=interactive)
            _render_result(result, json_output=json_output)
        except (AdapterError, DispatchError, RegistryError, OSError) as exc:
            _report_error(exc, original_args)
            return 2
        return 0

    namespace = parser.parse_args(args)
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
            result = _run_upgrade(namespace, registry)
        else:
            parser.print_help()
            return 0
        _render_result(result, json_output=json_output)
    except (
        ConfigError,
        ManifestError,
        RegistryError,
        RepositoryError,
        RunnerError,
        UpgradeError,
        OSError,
    ) as exc:
        _report_error(exc, original_args)
        return 2

    return 0
