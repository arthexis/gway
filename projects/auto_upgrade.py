"""Utilities supporting the auto-upgrade recipe.

The helpers in this module are invoked from ``recipes/auto_upgrade.gwr``
to coordinate logging, upgrades and system notifications.  They centralise
all stateful behaviour so the recipe itself can stay declarative and easy
to audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from gway import gw


LOG_NAME = "auto_upgrade.log"


def _bool_from(value) -> bool:
    """Return ``True`` when *value* represents an affirmative flag."""

    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if not text:
        return False
    return text in {"1", "true", "yes", "on", "force"}


def _latest_requested(explicit: bool | str | None = None) -> bool:
    """Determine whether the caller requested a ``--latest`` upgrade."""

    if explicit is not None:
        return _bool_from(explicit)

    for key in ("auto_upgrade_latest", "latest", "LATEST"):
        if key in gw.context:
            return _bool_from(gw.context[key])

    env_flag = os.environ.get("AUTO_UPGRADE_LATEST")
    if env_flag is not None:
        return _bool_from(env_flag)

    return "--latest" in sys.argv


def _log_path(log_name: str = LOG_NAME) -> Path:
    """Return the canonical path for the auto-upgrade log file."""

    return Path(gw.resource("logs", log_name, touch=True))


def _append_log(message: str, *, log_name: str = LOG_NAME) -> Path:
    """Append *message* to the auto-upgrade log and return the log path."""

    path = _log_path(log_name)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} | {message}\n")
    return path


def _installed_version() -> str | None:
    """Return the currently installed ``gway`` version, if available."""

    try:
        return metadata.version("gway")
    except metadata.PackageNotFoundError:  # pragma: no cover - defensive
        return None
    except Exception as exc:  # pragma: no cover - defensive logging
        gw.warning(f"Unable to determine installed gway version: {exc}")
        return None


def _broadcast(message: str) -> None:
    """Send *message* to logged-in users via ``wall`` when available."""

    try:
        subprocess.run(["wall", message], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        gw.debug("wall binary not available; skipping broadcast")
    except Exception as exc:  # pragma: no cover - best effort notification
        gw.debug(f"Failed to broadcast upgrade message: {exc}")


@dataclass(slots=True)
class CycleState:
    log_path: Path
    latest: bool
    previous_version: str | None


def log_cycle(*, latest: bool | str | None = None, log_name: str = LOG_NAME) -> CycleState:
    """Record a log entry for the start of a new upgrade check.

    The helper captures the currently installed version, records the check in
    ``logs/auto_upgrade.log`` and stores the details in ``gw.context`` for later
    recipe steps.
    """

    latest_requested = _latest_requested(latest)
    previous_version = _installed_version()

    log_message = "CHECK"
    details: list[str] = []
    if previous_version:
        details.append(f"installed={previous_version}")
    if latest_requested:
        details.append("latest=true")
    if details:
        log_message = f"{log_message} | {' '.join(details)}"

    log_path = _append_log(log_message, log_name=log_name)

    gw.context.update(
        {
            "auto_upgrade_latest": latest_requested,
            "auto_upgrade_previous_version": previous_version,
            "auto_upgrade_log": str(log_path),
        }
    )

    gw.info(f"[auto-upgrade] Logged check (latest={latest_requested}, version={previous_version})")
    return CycleState(log_path=log_path, latest=latest_requested, previous_version=previous_version)


def install(*, latest: bool | str | None = None) -> int:
    """Install or upgrade ``gway`` using the install builtin."""

    latest_requested = _latest_requested(latest)
    return gw.install("gway", mode="pip", latest=latest_requested)


def log_upgrade(
    *,
    version: str | None = None,
    latest: bool | str | None = None,
    log_name: str = LOG_NAME,
    notify: bool = True,
) -> dict:
    """Record the outcome of an applied upgrade and optionally notify users."""

    latest_requested = _latest_requested(latest)
    previous_version = gw.context.get("auto_upgrade_previous_version")
    current_version = version or _installed_version()

    if not current_version:
        log_message = "UPGRADE | version=unknown"
    else:
        log_message = f"UPGRADE | version={current_version}"
        if previous_version and previous_version != current_version:
            log_message += f" from={previous_version}"
        elif previous_version and previous_version == current_version and not latest_requested:
            log_message = f"UPGRADE-SKIPPED | version={current_version}"

    log_path = _append_log(log_message, log_name=log_name)

    gw.context.update(
        {
            "auto_upgrade_log": str(log_path),
            "auto_upgrade_current_version": current_version,
        }
    )

    gw.info(f"[auto-upgrade] Logged upgrade result: {log_message}")

    if notify and current_version and (latest_requested or previous_version != current_version):
        _broadcast(f"gway upgraded to {current_version}")

    return {
        "log": str(log_path),
        "version": current_version,
    }


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

