from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def _checkout_installer() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    installer = root / "install.sh"
    if installer.is_file() and (root / "pyproject.toml").is_file():
        return installer
    return None


def _bootstrap_system_install() -> int:
    installer = _checkout_installer()
    if installer is None:
        print(
            "gway: bare install can bootstrap GWAY only from a source checkout; "
            "use the documented system installer",
            file=sys.stderr,
        )
        return 2

    command = [str(installer)]
    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid) and geteuid() != 0:
        sudo = shutil.which("sudo")
        if sudo is None:
            print("gway: system installation requires root", file=sys.stderr)
            return 2
        command.insert(0, sudo)
    return subprocess.run(command, check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GWAY CLI with a noninteractive Git environment."""
    os.environ["GIT_TERMINAL_PROMPT"] = "0"

    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["install"] and os.environ.get("GWAY_SYSTEM_INSTALL") != "1":
        return _bootstrap_system_install()

    from .cli import main as cli_main

    return cli_main(argv)
