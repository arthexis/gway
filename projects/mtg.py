"""Deprecated Magic: The Gathering helpers."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Iterator

__all__ = ["scan_logs", "candidate_log_paths"]

_MESSAGE = "gw.mtg has been deprecated and is no longer available."


def _raise_deprecated() -> None:
    warnings.warn(
        "gw.mtg is deprecated and will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise RuntimeError(_MESSAGE)


def candidate_log_paths() -> Iterator[Path]:
    """Deprecated entry point."""

    _raise_deprecated()


def scan_logs(*, source: str | Path | None = None, limit: int | None = None) -> dict[str, object]:
    """Deprecated entry point."""

    _raise_deprecated()
    return {}
