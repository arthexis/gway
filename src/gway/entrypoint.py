from __future__ import annotations

import os
import sys
from collections.abc import Sequence

_JSON_MODE_ENV = "_GWAY_JSON_MODE"


def _global_json_requested(argv: Sequence[str]) -> bool:
    """Return whether the invocation enables GWAY's global JSON output mode."""
    for argument in argv:
        if argument == "--":
            break
        if argument == "--json":
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    """Seed invocation-wide output context before entering the normal bootstrap."""
    from .bootstrap import main as bootstrap_main

    arguments = list(sys.argv[1:] if argv is None else argv)
    previous = os.environ.get(_JSON_MODE_ENV)

    # A reload replaces the current process with ``gway --resume``. Preserve the
    # already-established mode across that process boundary instead of treating
    # the internal resume argv as a new user invocation.
    resuming = bool(arguments) and arguments[0] == "--resume"
    if not resuming or previous is None:
        os.environ[_JSON_MODE_ENV] = "1" if _global_json_requested(arguments) else "0"

    try:
        return bootstrap_main(arguments)
    finally:
        # Programmatic callers may invoke main() repeatedly in one process. Real
        # CLI invocations exit (or exec on reload), so restoring here is harmless
        # and prevents one invocation's output mode leaking into the next.
        if previous is None:
            os.environ.pop(_JSON_MODE_ENV, None)
        else:
            os.environ[_JSON_MODE_ENV] = previous


__all__ = ["main"]
