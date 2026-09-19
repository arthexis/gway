"""Executable targets that can be run directly or supervised as services."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Launchable:
    """One executable target independent of service lifecycle policy."""

    name: str
    kind: str
    command: tuple[str, ...]
    root: Path | None = None
    target: object = None
    metadata: object = field(default_factory=dict)

    def __post_init__(self):
        name = str(self.name).strip()
        kind = str(self.kind).strip()
        command = tuple(str(part) for part in self.command)
        if not name:
            raise ValueError("Launchable name cannot be empty")
        if not kind:
            raise ValueError("Launchable kind cannot be empty")
        if not command:
            raise ValueError("Launchable command cannot be empty")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "command", command)
        if self.root is not None:
            object.__setattr__(
                self,
                "root",
                Path(self.root).expanduser().resolve(),
            )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @classmethod
    def operation(cls, name, *, root=None, metadata=None):
        """Create a launchable that re-enters Gway through one operation."""
        parts = tuple(
            part
            for part in str(name).replace(" ", ".").split(".")
            if part
        )
        if not parts:
            raise ValueError("Operation launchable requires a name")
        return cls(
            name=".".join(parts),
            kind="operation",
            command=("{python}", "-m", "gway", *parts),
            root=root,
            target=".".join(parts),
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def recipe(cls, path, *, name=None, root=None, metadata=None):
        """Create a launchable that re-enters Gway through one recipe path."""
        path = Path(path).expanduser().resolve()
        return cls(
            name=name or path.stem,
            kind="recipe",
            command=("{python}", "-m", "gway", str(path)),
            root=root or path.parent,
            target=path,
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def command_target(cls, name, command, *, root=None, metadata=None):
        """Create a launchable around an already normalized command."""
        return cls(
            name=name,
            kind="command",
            command=tuple(command),
            root=root,
            target=tuple(command),
            metadata={} if metadata is None else metadata,
        )


class Launchables(Mapping):
    """Gateway-local index of known executable targets."""

    def __init__(self):
        self._items = {}

    def register(self, launchable):
        if not isinstance(launchable, Launchable):
            raise TypeError("launchable must be a Launchable")
        self._items[launchable.name] = launchable
        return launchable

    def operation(self, name, *, root=None, metadata=None):
        return self.register(
            Launchable.operation(name, root=root, metadata=metadata)
        )

    def recipe(self, path, *, name=None, root=None, metadata=None):
        return self.register(
            Launchable.recipe(
                path,
                name=name,
                root=root,
                metadata=metadata,
            )
        )

    def resolve(self, name, default=None):
        return self._items.get(str(name).replace(" ", "."), default)

    def __getitem__(self, name):
        return self._items[name]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)
