from __future__ import annotations

import argparse

from .. import __version__

CORE_COMMANDS = frozenset(
    {
        "list",
        "info",
        "path",
        "register",
        "install",
        "upgrade",
        "service",
        "shell",
        "solve",
        "recipe",
    }
)


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


__all__ = ["CORE_COMMANDS", "build_parser"]
