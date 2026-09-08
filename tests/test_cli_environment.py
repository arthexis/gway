from __future__ import annotations

import os
import subprocess
import sys


def _probe(argv0: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, sys; "
                f"sys.argv[0] = {argv0!r}; "
                "import gway; "
                "print(os.environ['GIT_TERMINAL_PROMPT'])"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_stale_gway_launcher_disables_git_terminal_prompt() -> None:
    assert _probe("/opt/gway/venv/bin/gway") == "0"


def test_library_import_does_not_change_git_terminal_prompt() -> None:
    assert _probe("pytest") == "1"
