"""GWAY project manager and command dispatcher."""

import os
import sys
from pathlib import Path

from .output_context import seed_legacy_cli_json_mode

# Older setuptools-generated launchers may still import gway.cli or
# gway.bootstrap directly. Detect the actual gway command before importing
# package internals so every CLI verb inherits noninteractive Git behavior and
# invocation-local JSON context even before the launcher itself is regenerated.
if Path(sys.argv[0]).name.lower() in {"gway", "gway.exe"}:
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    seed_legacy_cli_json_mode(sys.argv[1:])

from .api import Gway, gw, gway  # noqa: E402
from .outcome import CommandOutcome, SemanticFailure, failure, success  # noqa: E402
from .sigils import gway_context  # noqa: E402

__all__ = [
    "CommandOutcome",
    "Gway",
    "SemanticFailure",
    "failure",
    "gway",
    "gw",
    "gway_context",
    "success",
    "__version__",
]

__version__ = "1.0.1"
