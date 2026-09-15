from __future__ import annotations

import sys
from collections.abc import Sequence

from .output_context import json_mode_scope, resolve_cli_json_mode


def main(argv: Sequence[str] | None = None) -> int:
    """Apply invocation-local output context before entering the normal bootstrap."""
    from .bootstrap import main as bootstrap_main

    arguments = list(sys.argv[1:] if argv is None else argv)
    with json_mode_scope(resolve_cli_json_mode(arguments)):
        return bootstrap_main(arguments)


__all__ = ["main"]
