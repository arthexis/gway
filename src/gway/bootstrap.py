from __future__ import annotations

import os
import sys
from collections.abc import Sequence


def _normalize_upgrade_self_alias(argv: Sequence[str]) -> list[str]:
    """Treat the literal GWAY project name as the self-upgrade selector."""
    args = list(argv)
    try:
        upgrade_index = args.index("upgrade")
    except ValueError:
        return args

    for index in range(upgrade_index + 1, len(args)):
        argument = args[index]
        if argument == "--":
            break
        if argument.startswith("-"):
            continue
        if argument == "gway":
            args[index] = "--self"
        break
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GWAY CLI with a noninteractive Git environment."""
    os.environ["GIT_TERMINAL_PROMPT"] = "0"

    from .cli import main as cli_main

    arguments = sys.argv[1:] if argv is None else argv
    return cli_main(_normalize_upgrade_self_alias(arguments))
