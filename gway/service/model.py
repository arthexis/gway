"""Service lifecycle policy layered over generic launchables."""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from ..launchable import Launchable


@dataclass(frozen=True)
class Service:
    """Lifecycle policy attached to one executable launchable."""

    project: str
    name: str
    root: Path
    command: tuple[str, ...] = ()
    launchable: Launchable | None = None
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
        root = Path(self.root).expanduser().resolve()
        object.__setattr__(self, "root", root)

        launchable = self.launchable
        command = tuple(self.command)
        if launchable is None:
            if not command:
                raise ValueError("Service requires a launchable or command")
            launchable = Launchable.command_target(
                self.name,
                command,
                root=root,
                metadata={"project": self.project, "service": self.name},
            )
        elif command and tuple(launchable.command) != command:
            raise ValueError(
                "Service command must match its launchable command"
            )

        object.__setattr__(self, "launchable", launchable)
        object.__setattr__(self, "command", tuple(launchable.command))
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
