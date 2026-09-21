"""Stable managed-runtime identity for self-upgrade and reload decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .model import Installation
from .paths import install_paths
from .state import InstallState


@dataclass(frozen=True)
class RuntimeIdentity:
    """Normalized identity of one managed GWAY runtime."""

    source: str | None = None
    requested_ref: str | None = None
    resolved_revision: str | None = None
    fingerprint: str | None = None
    install_path: Path | None = None
    scope: str | None = None

    def __post_init__(self):
        if self.install_path is not None:
            object.__setattr__(
                self,
                "install_path",
                Path(self.install_path).expanduser().resolve(),
            )
        if self.scope is not None and self.scope not in {"user", "system"}:
            raise ValueError("runtime identity scope must be 'user' or 'system'")

    @property
    def comparable(self):
        """Return whether this identity has durable code identity information."""
        return bool(self.resolved_revision or self.fingerprint)

    def same_runtime(self, other):
        """Return whether two comparable identities describe the same code."""
        if not isinstance(other, RuntimeIdentity):
            return False
        if not self.comparable or not other.comparable:
            raise ValueError("runtime identities are not comparable")

        if (
            self.resolved_revision is not None
            and other.resolved_revision is not None
            and self.resolved_revision != other.resolved_revision
        ):
            return False

        if (
            self.fingerprint is not None
            and other.fingerprint is not None
            and self.fingerprint != other.fingerprint
        ):
            return False

        strong_overlap = (
            self.resolved_revision is not None
            and other.resolved_revision is not None
        ) or (
            self.fingerprint is not None
            and other.fingerprint is not None
        )
        if not strong_overlap:
            raise ValueError("runtime identities share no comparable code identity")

        return True

    def diagnostic(self):
        """Return a compact non-secret diagnostic identity string."""
        parts = []
        if self.resolved_revision:
            parts.append(f"revision={self.resolved_revision}")
        if self.fingerprint:
            parts.append(f"fingerprint={self.fingerprint}")
        if self.requested_ref:
            parts.append(f"ref={self.requested_ref}")
        if self.scope:
            parts.append(f"scope={self.scope}")
        return " ".join(parts) if parts else "unavailable"


def runtime_identity(installation):
    """Normalize one managed installation record into a RuntimeIdentity."""
    if not isinstance(installation, Installation):
        raise TypeError("runtime_identity requires an Installation record")
    return RuntimeIdentity(
        source=installation.source,
        requested_ref=installation.requested_ref,
        resolved_revision=installation.resolved_revision,
        fingerprint=installation.fingerprint,
        install_path=installation.install_path,
        scope=installation.scope,
    )


def managed_gway_identity(*, system=False, paths=None, state=None):
    """Return the currently managed GWAY identity, or None when not installed."""
    selected = install_paths(system=system) if paths is None else paths
    registry = InstallState(selected.state) if state is None else state
    installation = registry.get("gway", scope=selected.scope)
    if installation is None:
        return None
    return runtime_identity(installation)
