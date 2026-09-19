"""Declarative service definitions owned by managed Gway projects."""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Service:
    """Normalized declaration for one project-owned service."""

    project: str
    name: str
    root: Path
    command: tuple[str, ...]
    description: str | None = None
    working_directory: str | None = None
    writable_paths: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ()
    environment: object = field(default_factory=dict)
    restart: str | None = None
    restart_sec: float | None = None
    autostart: bool = False
    state_root: Path | None = None

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "writable_paths", tuple(self.writable_paths))
        object.__setattr__(self, "profiles", tuple(self.profiles))
        if self.state_root is not None:
            object.__setattr__(
                self,
                "state_root",
                Path(self.state_root).expanduser().resolve(),
            )
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(dict(self.environment)),
        )

    @property
    def identity(self):
        """Return the durable project/service identity."""
        return self.project, self.name


@dataclass(frozen=True)
class Catalog:
    """Normalized service declarations for one managed project."""

    project: str
    root: Path
    services: tuple[Service, ...] = ()
    profile_file: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())
        object.__setattr__(self, "services", tuple(self.services))

    def get(self, name):
        """Return one service declaration by name, or None."""
        return next(
            (service for service in self.services if service.name == name),
            None,
        )
