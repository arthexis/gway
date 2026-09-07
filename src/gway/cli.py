from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .project import ManifestError
from .registry import Registry, RegistryError


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = list(argv) if argv is not None else None
    if args == []:
        parser.print_help()
        return 0

    namespace = parser.parse_args(args)
    registry = Registry()

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
        else:
            parser.print_help()
    except (ManifestError, RegistryError) as exc:
        print(f"gway: {exc}", file=sys.stderr)
        return 2

    return 0
