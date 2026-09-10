from __future__ import annotations

import os
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GWAY CLI with a noninteractive Git environment."""
    os.environ["GIT_TERMINAL_PROMPT"] = "0"

    from .cli import main as cli_main

    return cli_main(argv)
