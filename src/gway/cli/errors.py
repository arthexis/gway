from __future__ import annotations

import errno
import os
import shlex
import shutil
import sys
from collections.abc import Sequence

from ..adapters import AdapterError
from ..config import ConfigError
from ..dispatcher import DispatchError
from ..expression import ExpressionError
from ..project import ManifestError
from ..recipe import RecipeError
from ..registry import RegistryError
from ..repository import RepositoryError
from ..runner import RunnerError
from ..service import ServiceError
from ..shell import ShellError
from ..stage import StageSyntaxError
from ..upgrade import UpgradeError

_PERMISSION_ERRNOS = frozenset({errno.EACCES, errno.EPERM})


def extract_global_flags(args: list[str]) -> tuple[list[str], bool, bool]:
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


def prompt_required_value(name: str) -> str:
    while True:
        print(f"{name}: ", end="", file=sys.stderr, flush=True)
        value = input()
        if value:
            return value
        print("A value is required.", file=sys.stderr)


def permission_failure(exc: BaseException) -> OSError | None:
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


def can_suggest_sudo() -> bool:
    if os.name != "posix" or shutil.which("sudo") is None:
        return False
    geteuid = getattr(os, "geteuid", None)
    return not callable(geteuid) or geteuid() != 0


def report_error(exc: BaseException, args: Sequence[str]) -> None:
    print(f"gway: {exc}", file=sys.stderr)
    if permission_failure(exc) is not None and can_suggest_sudo():
        command = shlex.join(["gway", *args])
        print(f"hint: try running with sudo: sudo {command}", file=sys.stderr)


def known_cli_error(exc: BaseException) -> bool:
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


def handle_cli_exception(exc: Exception, args: Sequence[str]) -> int:
    if not known_cli_error(exc) and permission_failure(exc) is None:
        raise exc
    report_error(exc, args)
    return 2


def managed_result_name(project_name: str, project_args: Sequence[str]) -> str:
    if project_args:
        command_name = project_args[0]
        if command_name and not command_name.startswith("-"):
            return command_name.replace("-", "_")
    return project_name.replace("-", "_")
