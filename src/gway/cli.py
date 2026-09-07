from __future__ import annotations

import argparse
import errno
import json
import os
import shlex
import shutil
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import version as distribution_version

from . import __version__
from .adapters import AdapterError
from .config import ConfigError
from .dispatcher import Dispatcher, DispatchError
from .install import Installer
from .project import ManifestError
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


def _print_info(registry: Registry, name: str) -> None:
    project = registry.require(name)
    print(f"name: {project.name}")
    print(f"path: {project.path}")
    print(f"adapter: {project.adapter_type}")
    if project.aliases:
        print(f"aliases: {', '.join(project.aliases)}")
    if project.repository:
        print(f"repository: {project.repository}")
    if project.revision:
        print(f"revision: {project.revision}")


def _print_project_help(dispatcher: Dispatcher, project_name: str) -> None:
    project = dispatcher.registry.require(project_name)
    commands = dispatcher.commands(project_name)
    print(f"usage: gway {project.name} <command> [arguments]")
    print()
    print("commands:")
    for command in commands:
        name = " ".join(command.path)
        if command.summary:
            print(f"  {name:<24} {command.summary}")
        else:
            print(f"  {name}")


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


def _extract_json_flag(args: list[str]) -> tuple[list[str], bool]:
    json_output = "--json" in args
    if not json_output:
        return args, False
    return [arg for arg in args if arg != "--json"], True


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


def _install_runtime_component(name: str) -> bool:
    distribution = RUNTIME_COMPONENTS.get(name)
    if distribution is None:
        return False
    print(f"installed {name}\t{distribution}@{distribution_version(distribution)}")
    return True


def _run_upgrade(namespace: argparse.Namespace, registry: Registry) -> None:
    if namespace.project and (namespace.all or namespace.upgrade_self):
        raise UpgradeError("PROJECT cannot be combined with --all or --self")

    upgrader = Upgrader(registry)
    if namespace.project:
        project = upgrader.project(namespace.project, force=namespace.force)
        print(f"upgraded {project.name}\t{project.repository}@{project.revision}")
        return

    bare = not namespace.all and not namespace.upgrade_self
    if bare or namespace.upgrade_self:
        upgrader.upgrade_self()
        print("upgraded gway\tarthexis/gway@main")

    if bare or namespace.all:
        for project in upgrader.all_projects(force=namespace.force):
            print(f"upgraded {project.name}\t{project.repository}@{project.revision}")


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    parser = build_parser()
    original_args = list(sys.argv[1:] if argv is None else argv)
    args, json_output = _extract_json_flag(original_args)
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
            result = active_dispatcher.run(args[0], project_args)
            _render_result(result, json_output=json_output)
        except (AdapterError, DispatchError, RegistryError, OSError) as exc:
            _report_error(exc, original_args)
            return 2
        return 0

    namespace = parser.parse_args(args)
    registry = active_dispatcher.registry

    try:
        if namespace.command == "list":
            for project in registry.list():
                aliases = f" ({', '.join(project.aliases)})" if project.aliases else ""
                print(f"{project.name}{aliases}\t{project.path}")
        elif namespace.command == "info":
            _print_info(registry, namespace.project)
        elif namespace.command == "path":
            print(registry.require(namespace.project).path)
        elif namespace.command == "register":
            project = registry.register_path(namespace.path)
            print(f"registered {project.name}\t{project.path}")
        elif namespace.command == "install":
            if not _install_runtime_component(namespace.project):
                project = Installer(registry).install(namespace.project)
                print(f"installed {project.name}\t{project.repository}@{project.revision}")
        elif namespace.command == "upgrade":
            _run_upgrade(namespace, registry)
        else:
            parser.print_help()
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
