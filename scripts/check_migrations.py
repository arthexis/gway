#!/usr/bin/env python3
"""Lightweight migration check helper used by CI pipelines.

The helper mirrors ``manage.py makemigrations --check`` when a Django project
is present in the repository.  Repositories that do not ship a Django project
can still invoke the script safely; it will simply skip the check.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _detect_manage_py(repo_root: Path) -> Path | None:
    """Return the path to ``manage.py`` if a Django project exists."""

    candidate = repo_root / "manage.py"
    if candidate.exists():
        return candidate
    env_candidate = os.environ.get("DJANGO_MANAGEPY")
    if env_candidate:
        path = Path(env_candidate)
        if path.exists():
            return path
    return None


def _run_makemigrations(manage_py: Path, *, check_only: bool = True) -> int:
    """Run ``makemigrations`` and return the exit status."""

    args = [sys.executable, str(manage_py), "makemigrations"]
    if check_only:
        args.extend(["--check", "--dry-run"])
    proc = subprocess.run(args, cwd=manage_py.parent)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manage",
        dest="manage_path",
        help="Explicit path to manage.py (defaults to repository root)",
    )
    parser.add_argument(
        "--no-check",
        dest="check_only",
        action="store_false",
        help="Apply migrations instead of running in check-only mode",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    manage_py = Path(args.manage_path) if args.manage_path else _detect_manage_py(repo_root)
    if not manage_py:
        print("No Django manage.py detected; skipping migration check.")
        return 0

    return _run_makemigrations(manage_py, check_only=args.check_only)


if __name__ == "__main__":  # pragma: no cover - convenience script
    raise SystemExit(main())
