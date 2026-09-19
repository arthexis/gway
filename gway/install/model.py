"""Durable installation records."""

from dataclasses import dataclass, replace
from pathlib import Path


def validate_name(value):
    """Return one safe managed-project name."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("installation name must be a non-empty string")
    if value != value.strip():
        raise ValueError("installation name cannot have surrounding whitespace")
    if value in {".", ".."} or "/" in value or "\\" in value or "\0" in value:
        raise ValueError("installation name must be one safe path component")
    return value


@dataclass(frozen=True)
class Installation:
    """Authoritative record for one managed project installation."""

    name: str
    source: str
    install_path: Path
    scope: str = "user"
    requested_ref: str | None = None
    resolved_revision: str | None = None
    fingerprint: str | None = None
    installed_at: str | None = None

    def __post_init__(self):
        validate_name(self.name)
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("installation source must be a non-empty string")
        if self.scope not in {"user", "system"}:
            raise ValueError("installation scope must be 'user' or 'system'")
        object.__setattr__(self, "install_path", Path(self.install_path))

    def with_installed_at(self, value):
        """Return this record with a durable installation timestamp."""
        return replace(self, installed_at=value)


@dataclass(frozen=True)
class InstallRequest:
    """Normalized desired-state request for the install operation."""

    source: str
    ref: str | None = None
    upgrade: bool = True
    force: bool = False
    stash: bool = False
    system: bool = False
    services: tuple[str, ...] = ()
    name: str | None = None
    backend: str = "systemd"

    def __post_init__(self):
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("install source must be a non-empty string")
        if self.force and self.stash:
            raise ValueError("--force and --stash are mutually exclusive")
        values = self.services
        if isinstance(values, str):
            values = tuple(part.strip() for part in values.split(","))
        else:
            values = tuple(values)
        names = []
        for name in values:
            validate_name(name)
            if name not in names:
                names.append(name)
        object.__setattr__(self, "services", tuple(names))
        if not isinstance(self.backend, str) or not self.backend.strip():
            raise ValueError("--backend must be a non-empty string")
        from .backends import get as get_backend

        get_backend(self.backend)

        if self.name is not None:
            validate_name(self.name.removesuffix(".service"))
            if len(self.services) != 1:
                raise ValueError("--name requires exactly one selected service")

    @property
    def scope(self):
        return "system" if self.system else "user"


@dataclass(frozen=True)
class UninstallRequest:
    """Normalized desired-state request for the uninstall operation."""

    project: str
    system: bool = False

    def __post_init__(self):
        if not isinstance(self.project, str) or not self.project.strip():
            raise ValueError("uninstall project must be a non-empty string")

    @property
    def scope(self):
        return "system" if self.system else "user"
