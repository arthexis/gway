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
    launchable: Launchable
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

        if not isinstance(self.launchable, Launchable):
            raise TypeError("Service launchable must be a Launchable")
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

    @classmethod
    def from_launchable(cls, project, name, root, launchable, **policy):
        """Attach service lifecycle policy to an existing launchable."""
        return cls(
            project=project,
            name=name,
            root=root,
            launchable=launchable,
            **policy,
        )

    @property
    def identity(self):
        """Return the durable project/service identity."""
        return self.project, self.name

