from __future__ import annotations

import shutil
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


def _remove_python_bytecode(checkout: Path) -> None:
    """Remove ignored Python caches that can preserve deleted importable modules."""
    try:
        for cache in checkout.rglob("__pycache__"):
            if cache.is_dir() and not cache.is_symlink():
                shutil.rmtree(cache)
        for suffix in ("*.pyc", "*.pyo"):
            for bytecode in checkout.rglob(suffix):
                if bytecode.is_file() and not bytecode.is_symlink():
                    bytecode.unlink()
    except OSError as exc:
        raise RepositoryError(
            f"cannot remove Python bytecode from managed checkout {checkout}: {exc}"
        ) from exc


def clean_managed_checkout(
    checkout: Path,
    full_name: str,
    repositories: RepositoryManager,
) -> None:
    """Remove stale code while preserving ignored application/runtime state."""
    repositories.validate_checkout(checkout, full_name)
    Runner.configure_managed_checkout(checkout)
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

    # git clean intentionally preserves ignored files. Python bytecode is ignored by
    # most projects, but sourceless .pyc files can remain importable after their .py
    # module was deleted upstream. Purge only Python caches; keep all other ignored
    # state (databases, media, locks, local configuration, and similar data) intact.
    _remove_python_bytecode(checkout)
