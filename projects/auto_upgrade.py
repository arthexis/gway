"""Gateway auto-upgrade helpers (compatibility shim).

The Gateway-specific implementation now lives in :mod:`projects.package.gway` so
other packages can reuse the shared upgrade plumbing exposed by
:mod:`projects.package`. This module simply re-exports the ``gway`` sub-project
for backwards compatibility with existing recipes and imports.
"""

from __future__ import annotations

from gway import gw
from gway.projects import package
from gway.projects.package import gway as _gway

__all__ = [
    "LOG_NAME",
    "CONFIG",
    "CycleState",
    "log_cycle",
    "install",
    "log_upgrade",
    "_current_release",
    "notify_upgrade",
]

LOG_NAME = _gway.LOG_NAME
CONFIG = _gway.CONFIG
CycleState = _gway.CycleState

# Preserve the helper hooks that tests patch directly.
_broadcast = _gway._broadcast
_release_lookup = _gway._release_lookup
_normalise_release = _gway._normalise_release


def log_cycle(*, latest: bool | str | None = None, log_name: str = LOG_NAME) -> CycleState:
    """Record a log entry for the start of a new upgrade check."""

    return package.log_cycle(CONFIG, latest=latest, log_name=log_name)


def install(*, latest: bool | str | None = None) -> int:
    """Install or upgrade ``gway`` using the install builtin."""

    return package.install(CONFIG, latest=latest)


def log_upgrade(
    *,
    version: str | None = None,
    latest: bool | str | None = None,
    log_name: str = LOG_NAME,
    notify: bool = True,
    broadcaster=None,
) -> dict:
    """Record the outcome of an applied upgrade and optionally notify users."""

    active = broadcaster if broadcaster is not None else (_broadcast if notify else None)
    return package.log_upgrade(
        CONFIG,
        version=version,
        latest=latest,
        log_name=log_name,
        notify=notify,
        broadcaster=active,
    )


def _current_release(length: int = 6) -> str | None:
    """Return the current build identifier if available."""

    return package.current_release(CONFIG, length=length)


def notify_upgrade(
    *,
    version: str | None = None,
    release: str | None = None,
    latest: bool | str | None = None,
    timestamp=None,
    timeout: int = 20,
) -> dict:
    """Display a toast/LCD message summarising a successful upgrade."""

    return package.notify_upgrade(
        CONFIG,
        version=version,
        release=release,
        latest=latest,
        timestamp=timestamp,
        timeout=timeout,
        release_lookup=_current_release,
    )

