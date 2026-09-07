from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = list(argv) if argv is not None else None
    if args == []:
        parser.print_help()
        return 0
    parser.parse_args(args)
    return 0
