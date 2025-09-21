"""Reusable helpers for package auto-upgrade recipes.

The utilities in this module encapsulate the generic pieces needed for an
auto-upgrade workflow: logging, detecting ``--latest`` requests, invoking an
installer and notifying users when a new build becomes available.  Individual
projects can tailor the behaviour by providing a :class:`UpgradeConfig` instance
with package-specific settings (package name, log naming, release discovery,
notification templates, etc.).

``projects/package/gway.py`` demonstrates how the helpers can be wrapped to
serve the traditional Gateway upgrade recipe while remaining customisable for
other packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import sys
from importlib import metadata
from pathlib import Path
from typing import Callable

from gway import gw

__all__ = [
    "UpgradeConfig",
    "CycleState",
    "log_cycle",
    "install",
    "log_upgrade",
    "notify_upgrade",
    "current_release",
]


@dataclass(slots=True)
class UpgradeConfig:
    """Settings that tailor the upgrade helpers for a specific package."""

    package: str
    distribution: str | None = None
    log_name: str = "auto_upgrade.log"
    context_prefix: str = "auto_upgrade"
    install_mode: str = "pip"
    env_latest_var: str = "AUTO_UPGRADE_LATEST"
    broadcast_template: str = "{package} upgraded to {version}"
    notify_title_template: str = "{package} v{version} r{release}"
    notify_time_format: str = "%Y%m%d %H:%M"
    release_length: int = 6
    release_lookup: Callable[[int], str | None] | None = None
    release_normalizer: Callable[[str | None], str | None] | None = None
    fallback_release: str = "000000"

    def __post_init__(self) -> None:
        if not self.distribution:
            self.distribution = self.package


@dataclass(slots=True)
class CycleState:
    """State returned from :func:`log_cycle` for recipe chaining."""

    log_path: Path
    latest: bool
    previous_version: str | None


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


def _context_key(config: UpgradeConfig, suffix: str) -> str:
    prefix = config.context_prefix.strip()
    if not prefix:
        return suffix
    return f"{prefix}_{suffix}"


def _latest_requested(config: UpgradeConfig, explicit: bool | str | None = None) -> bool:
    """Determine whether the caller requested a ``--latest`` upgrade."""

    if explicit is not None:
        return _bool_from(explicit)

    context_key = _context_key(config, "latest")
    if context_key in gw.context:
        return _bool_from(gw.context[context_key])

    for key in ("latest", "LATEST"):
        if key in gw.context:
            return _bool_from(gw.context[key])

    env_flag = os.environ.get(config.env_latest_var)
    if env_flag is not None:
        return _bool_from(env_flag)

    return "--latest" in sys.argv


def _log_path(config: UpgradeConfig, log_name: str | None = None) -> Path:
    """Return the canonical path for the upgrade log file."""

    effective_name = log_name or config.log_name
    return Path(gw.resource("logs", effective_name, touch=True))


def _append_log(config: UpgradeConfig, message: str, *, log_name: str | None = None) -> Path:
    """Append *message* to the configured log and return the log path."""

    path = _log_path(config, log_name)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} | {message}\n")
    return path


def _installed_version(config: UpgradeConfig) -> str | None:
    """Return the currently installed version for ``config.distribution``."""

    try:
        distribution = config.distribution or config.package
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:  # pragma: no cover - defensive
        return None
    except Exception as exc:  # pragma: no cover - defensive logging
        gw.warning(
            f"Unable to determine installed {config.distribution or config.package} version: {exc}"
        )
        return None


def log_cycle(
    config: UpgradeConfig,
    *,
    latest: bool | str | None = None,
    log_name: str | None = None,
) -> CycleState:
    """Record a log entry for the start of a new upgrade check."""

    latest_requested = _latest_requested(config, latest)
    previous_version = _installed_version(config)

    log_message = "CHECK"
    details: list[str] = []
    if previous_version:
        details.append(f"installed={previous_version}")
    if latest_requested:
        details.append("latest=true")
    if details:
        log_message = f"{log_message} | {' '.join(details)}"

    log_path = _append_log(config, log_message, log_name=log_name)

    gw.context.update(
        {
            _context_key(config, "latest"): latest_requested,
            _context_key(config, "previous_version"): previous_version,
            _context_key(config, "log"): str(log_path),
        }
    )

    gw.info(
        f"[{config.context_prefix}] Logged check (latest={latest_requested}, version={previous_version})"
    )
    return CycleState(
        log_path=log_path,
        latest=latest_requested,
        previous_version=previous_version,
    )


def install(
    config: UpgradeConfig,
    *,
    latest: bool | str | None = None,
    package: str | None = None,
    mode: str | None = None,
    **kwargs,
) -> int:
    """Install or upgrade ``config.package`` using the install builtin."""

    latest_requested = _latest_requested(config, latest)
    package_name = package or config.package
    install_mode = mode or config.install_mode
    return gw.install(package_name, mode=install_mode, latest=latest_requested, **kwargs)


def log_upgrade(
    config: UpgradeConfig,
    *,
    version: str | None = None,
    latest: bool | str | None = None,
    log_name: str | None = None,
    notify: bool = True,
    broadcaster: Callable[[str], None] | None = None,
) -> dict:
    """Record the outcome of an applied upgrade and optionally notify users."""

    latest_requested = _latest_requested(config, latest)
    previous_key = _context_key(config, "previous_version")
    previous_version = gw.context.get(previous_key)
    current_version = version or _installed_version(config)

    if not current_version:
        log_message = "UPGRADE | version=unknown"
    else:
        log_message = f"UPGRADE | version={current_version}"
        if previous_version and previous_version != current_version:
            log_message += f" from={previous_version}"
        elif previous_version and previous_version == current_version and not latest_requested:
            log_message = f"UPGRADE-SKIPPED | version={current_version}"

    log_path = _append_log(config, log_message, log_name=log_name)

    gw.context.update(
        {
            _context_key(config, "log"): str(log_path),
            _context_key(config, "current_version"): current_version,
        }
    )

    gw.info(f"[{config.context_prefix}] Logged upgrade result: {log_message}")

    should_notify = (
        notify
        and broadcaster is not None
        and current_version
        and (latest_requested or previous_version != current_version)
    )
    if should_notify:
        message = config.broadcast_template.format(
            package=config.package,
            version=current_version,
            previous=previous_version,
        )
        try:
            broadcaster(message)
        except Exception as exc:  # pragma: no cover - best effort broadcast
            gw.debug(f"[{config.context_prefix}] Broadcast failed: {exc}")

    return {
        "log": str(log_path),
        "version": current_version,
    }


def current_release(
    config: UpgradeConfig,
    *,
    release_lookup: Callable[[int], str | None] | None = None,
    length: int | None = None,
) -> str | None:
    """Return the current build identifier if available."""

    lookup = release_lookup or config.release_lookup
    if lookup is None:
        return None

    try:
        release = lookup(length or config.release_length)
    except Exception as exc:  # pragma: no cover - best effort helper
        gw.debug(f"[{config.context_prefix}] Unable to determine build identifier: {exc}")
        return None

    release_text = str(release or "").strip()
    if not release_text or release_text.lower() == "unknown":
        return None

    normaliser = config.release_normalizer
    if normaliser is not None:
        try:
            release_text = normaliser(release_text)
        except Exception as exc:  # pragma: no cover - defensive normalisation
            gw.debug(f"[{config.context_prefix}] Failed to normalise release: {exc}")

    return release_text or None


def notify_upgrade(
    config: UpgradeConfig,
    *,
    version: str | None = None,
    release: str | None = None,
    latest: bool | str | None = None,
    timestamp: datetime | None = None,
    timeout: int = 20,
    release_lookup: Callable[[int], str | None] | None = None,
) -> dict:
    """Display a toast/LCD message summarising a successful upgrade."""

    latest_requested = _latest_requested(config, latest)
    previous_key = _context_key(config, "previous_version")
    current_key = _context_key(config, "current_version")
    previous_version = gw.context.get(previous_key)
    current_version = version or gw.context.get(current_key) or _installed_version(config)

    if not current_version:
        gw.debug(f"[{config.context_prefix}] Skipping notification: current version unknown")
        return {"status": "skipped", "reason": "unknown-version"}

    if not (latest_requested or previous_version != current_version):
        gw.debug(f"[{config.context_prefix}] Skipping notification: version unchanged")
        return {
            "status": "skipped",
            "reason": "version-unchanged",
            "version": current_version,
        }

    release_id = release or current_release(config, release_lookup=release_lookup)
    if not release_id:
        release_id = config.fallback_release

    subject = config.notify_title_template.format(
        package=config.package,
        version=current_version,
        release=release_id,
    )
    moment = timestamp or datetime.now()
    body = moment.strftime(config.notify_time_format)

    try:
        channel = gw.notify(body, title=subject, timeout=timeout)
    except Exception as exc:  # pragma: no cover - defensive
        gw.warning(
            f"[{config.context_prefix}] Failed to emit upgrade notification: {exc}"
        )
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

    gw.context[_context_key(config, "notification")] = summary
    gw.info(
        f"[{config.context_prefix}] Sent upgrade notification"
        f" (channel={channel}, version={current_version}, release={release_id})"
    )

    return summary
