from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .adapters import AdapterError
from .config import ConfigError
from .dispatcher import Dispatcher, DispatchError
from .install import Installer
from .project import ManifestError
from .registry import Registry, RegistryError
from .repository import RepositoryError
from .runner import RunnerError

CORE_COMMANDS = frozenset({"list", "info", "path", "register", "install"})


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
        help="Install a trusted GitHub project.",
    )
    install.add_argument("project")

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


def _render_result(result: object, *, json_output: bool = False) -> None:
    if result is None:
        return
    if json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result)


def main(argv: Sequence[str] | None = None, *, dispatcher: Dispatcher | None = None) -> int:
    parser = build_parser()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        parser.print_help()
        return 0

    active_dispatcher = dispatcher or Dispatcher()
    if args[0] not in CORE_COMMANDS and not args[0].startswith("-"):
        project_args = list(args[1:])
        json_output = False
        if "--json" in project_args:
            project_args.remove("--json")
            json_output = True
        try:
            result = active_dispatcher.run(args[0], project_args)
            _render_result(result, json_output=json_output)
        except (AdapterError, DispatchError, RegistryError) as exc:
            print(f"gway: {exc}", file=sys.stderr)
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
            project = Installer(registry).install(namespace.project)
            print(f"installed {project.name}\t{project.repository}@{project.revision}")
        else:
            parser.print_help()
    except (
        ConfigError,
        ManifestError,
        RegistryError,
        RepositoryError,
        RunnerError,
    ) as exc:
        print(f"gway: {exc}", file=sys.stderr)
        return 2

    return 0
