"""Gateway-specific package upgrade helpers."""

from __future__ import annotations

import subprocess

from gway import gw

from . import (
    CycleState,
    UpgradeConfig,
    current_release as _current_release,
    install as _install,
    log_cycle as _log_cycle,
    log_upgrade as _log_upgrade,
    notify_upgrade as _notify_upgrade,
)

__all__ = [
    "LOG_NAME",
    "CONFIG",
    "CycleState",
    "log_cycle",
    "install",
    "log_upgrade",
    "current_release",
    "notify_upgrade",
]

LOG_NAME = "auto_upgrade.log"


def _broadcast(message: str) -> None:
    """Send *message* to logged-in users via ``wall`` when available."""

    try:
        subprocess.run(
            ["wall", message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        gw.debug("wall binary not available; skipping broadcast")
    except Exception as exc:  # pragma: no cover - best effort notification
        gw.debug(f"Failed to broadcast upgrade message: {exc}")


def _release_lookup(length: int) -> str | None:
    try:
        return gw.hub.get_build(length=length)
    except Exception as exc:  # pragma: no cover - best effort helper
        gw.debug(f"Unable to determine build identifier: {exc}")
        return None


def _normalise_release(release: str | None) -> str | None:
    if not release:
        return None
    return release.lstrip("rR").upper()


CONFIG = UpgradeConfig(
    package="gway",
    log_name=LOG_NAME,
    context_prefix="auto_upgrade",
    install_mode="pip",
    env_latest_var="AUTO_UPGRADE_LATEST",
    broadcast_template="gway upgraded to {version}",
    notify_title_template="gway v{version} r{release}",
    notify_time_format="%Y%m%d %H:%M",
    release_length=6,
    release_lookup=_release_lookup,
    release_normalizer=_normalise_release,
    fallback_release="000000",
)


def log_cycle(*, latest: bool | str | None = None, log_name: str = LOG_NAME) -> CycleState:
    """Record a log entry for the start of a new Gateway upgrade check."""

    return _log_cycle(CONFIG, latest=latest, log_name=log_name)


def install(*, latest: bool | str | None = None) -> int:
    """Install or upgrade ``gway`` using the install builtin."""

    return _install(CONFIG, latest=latest)


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
    return _log_upgrade(
        CONFIG,
        version=version,
        latest=latest,
        log_name=log_name,
        notify=notify,
        broadcaster=active,
    )


def current_release(length: int = 6) -> str | None:
    """Return the current build identifier if available."""

    return _current_release(CONFIG, length=length)


def notify_upgrade(
    *,
    version: str | None = None,
    release: str | None = None,
    latest: bool | str | None = None,
    timestamp=None,
    timeout: int = 20,
) -> dict:
    """Display a toast/LCD message summarising a successful upgrade."""

    return _notify_upgrade(
        CONFIG,
        version=version,
        release=release,
        latest=latest,
        timestamp=timestamp,
        timeout=timeout,
    )

