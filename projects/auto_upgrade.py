"""Gateway auto-upgrade helpers (compatibility shim).

The Gateway-specific implementation now lives in :mod:`projects.package.gway` so
other packages can reuse the shared upgrade plumbing exposed by
:mod:`projects.package`.  This module simply re-exports the ``gway`` sub-project
for backwards compatibility with existing recipes and imports.
"""

from __future__ import annotations

from gway import gw
from gway.projects import package
from gway.projects.package import gway as _gway

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
) -> dict:
    """Record the outcome of an applied upgrade and optionally notify users."""

    broadcaster = _broadcast if notify else None
    return package.log_upgrade(
        CONFIG,
        version=version,
        latest=latest,
        log_name=log_name,
        notify=notify,
        broadcaster=broadcaster,
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
    )


def _current_release(length: int = 6) -> str | None:
    """Return the current build identifier if available."""

    try:
        release = gw.hub.get_build(length=length)
    except Exception as exc:  # pragma: no cover - best effort helper
        gw.debug(f"Unable to determine build identifier: {exc}")
        return None

    release = str(release or "").strip()
    if not release or release.lower() == "unknown":
        return None

    return release


def notify_upgrade(
    *,
    version: str | None = None,
    release: str | None = None,
    latest: bool | str | None = None,
    timestamp: datetime | None = None,
    timeout: int = 20,
) -> dict:
    """Display a toast/LCD message summarising a successful upgrade."""

    latest_requested = _latest_requested(latest)
    previous_version = gw.context.get("auto_upgrade_previous_version")
    current_version = (
        version
        or gw.context.get("auto_upgrade_current_version")
        or _installed_version()
    )

    if not current_version:
        gw.debug("[auto-upgrade] Skipping notification: current version unknown")
        return {"status": "skipped", "reason": "unknown-version"}

    if not (latest_requested or previous_version != current_version):
        gw.debug("[auto-upgrade] Skipping notification: version unchanged")
        return {
            "status": "skipped",
            "reason": "version-unchanged",
            "version": current_version,
        }

    release_id = release or _current_release()
    if release_id:
        release_id = release_id.lstrip("rR").upper()
    else:
        release_id = "000000"

    subject = f"gway v{current_version} r{release_id}"
    moment = timestamp or datetime.now()
    body = moment.strftime("%Y%m%d %H:%M")

    try:
        channel = gw.notify(body, title=subject, timeout=timeout)
    except Exception as exc:  # pragma: no cover - defensive
        gw.warning(f"[auto-upgrade] Failed to emit upgrade notification: {exc}")
        return {
            "status": "error",
            "version": current_version,
            "release": release_id,
            "message": body,
        }

    summary = {
        "status": "notified",
        "channel": channel,
        "version": current_version,
        "release": release_id,
        "title": subject,
        "message": body,
    }

    gw.context["auto_upgrade_notification"] = summary
    gw.info(
        "[auto-upgrade] Sent upgrade notification"
        f" (channel={channel}, version={current_version}, release={release_id})"
    )

    return summary

