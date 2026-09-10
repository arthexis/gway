from __future__ import annotations

import os
import sys
from collections.abc import Sequence

_GLOBAL_FLAGS = frozenset({"--json", "-i", "--interactive"})


def _normalize_install_args(argv: Sequence[str] | None) -> tuple[list[str] | None, int | None]:
    if argv is None:
        args = list(sys.argv[1:])
    else:
        args = list(argv)

    global_flags: list[str] = []
    command_args: list[str] = []
    literal = False
    for arg in args:
        if not literal and arg == "--":
            literal = True
            command_args.append(arg)
        elif not literal and arg in _GLOBAL_FLAGS:
            global_flags.append(arg)
        else:
            command_args.append(arg)

    if command_args == ["install"]:
        print("usage: gway install [-h] [--service] [--self] [project]", file=sys.stderr)
        print(
            "gway install: error: the following arguments are required: project",
            file=sys.stderr,
        )
        print(
            "hint: use 'gway install --self' or 'gway install gway' to install GWAY itself",
            file=sys.stderr,
        )
        return None, 2

    if command_args in (["install", "--self"], ["install", "gway"]):
        return [*global_flags, "upgrade", "gway"], None

    return args, None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GWAY CLI with a noninteractive Git environment."""
    os.environ["GIT_TERMINAL_PROMPT"] = "0"

    normalized, early_result = _normalize_install_args(argv)
    if early_result is not None:
        return early_result

    from .cli import main as cli_main

    return cli_main(normalized)
