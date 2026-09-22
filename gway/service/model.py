"""Service lifecycle policy layered over generic launchables."""

from dataclasses import dataclass
from pathlib import Path

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
    environment: tuple[str, ...] = ()
    restart: str = "on-failure"
    attempts: int = 3
    restart_sec: float = 5.0
    state_root: Path | None = None

    def __post_init__(self):
        root = Path(self.root).expanduser().resolve()
        object.__setattr__(self, "root", root)

        if not isinstance(self.launchable, Launchable):
            raise TypeError("Service launchable must be a Launchable")
        environment = (
            (self.environment,)
            if isinstance(self.environment, str)
            else tuple(self.environment)
        )
        normalized_environment = []
        for assignment in environment:
            assignment = str(assignment)
            name, separator, _ = assignment.partition("=")
            if (
                not separator
                or not name
                or "\x00" in assignment
                or "\n" in assignment
                or "\r" in assignment
            ):
                raise ValueError(
                    "Service environment entries must be NAME=value assignments"
                )
            normalized_environment.append(assignment)
        object.__setattr__(self, "environment", tuple(normalized_environment))
        if not isinstance(self.attempts, int) or isinstance(self.attempts, bool):
            raise TypeError("Service attempts must be an integer")
        if self.attempts < 0:
            raise ValueError("Service attempts cannot be negative")
        if self.restart not in {"on-failure", "always", "no"}:
            raise ValueError(f"Unsupported service restart policy: {self.restart!r}")
        if self.restart_sec < 0:
            raise ValueError("Service restart_sec cannot be negative")
        if self.state_root is not None:
            object.__setattr__(
                self,
                "state_root",
                Path(self.state_root).expanduser().resolve(),
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
