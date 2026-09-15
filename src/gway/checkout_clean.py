from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from .repository import RepositoryError, RepositoryManager
from .runner import Runner


def split_clean_arguments(
    arguments: Sequence[str],
    *,
    default: bool = True,
) -> tuple[bool, tuple[str, ...]]:
    """Extract Gway's clean override without leaking it to project lifecycle hooks."""
    clean = default
    passthrough: list[str] = []
    for argument in arguments:
        if argument == "--clean":
            clean = True
            continue
        if argument == "--no-clean":
            clean = False
            continue
        passthrough.append(argument)
    return clean, tuple(passthrough)


def clean_managed_checkout(
    checkout: Path,
    full_name: str,
    repositories: RepositoryManager,
) -> None:
    """Remove untracked, non-ignored files from a validated managed checkout."""
    Runner.configure_managed_checkout(checkout)
    repositories.validate_checkout(checkout, full_name)
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "clean", "-fd"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RepositoryError(f"cannot clean managed checkout {checkout}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git clean -fd failed"
        raise RepositoryError(f"cannot clean managed checkout {checkout}: {detail}")
