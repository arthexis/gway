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
    def operation(cls, name, *, arguments=(), root=None, metadata=None):
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
            command=(
                "{python}",
                "-m",
                "gway",
                *parts,
                *(str(argument) for argument in arguments),
            ),
            root=root,
            target=".".join(parts),
            metadata={} if metadata is None else metadata,
        )

    @classmethod
    def recipe(
        cls,
        path,
        *,
        arguments=(),
        name=None,
        root=None,
        metadata=None,
    ):
        """Create a launchable that re-enters Gway through one recipe path."""
        path = Path(path).expanduser().resolve()
        return cls(
            name=name or path.stem,
            kind="recipe",
            command=(
                "{python}",
                "-m",
                "gway",
                str(path),
                *(str(argument) for argument in arguments),
            ),
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

    def operation(
        self,
        name,
        *,
        arguments=(),
        root=None,
        metadata=None,
    ):
        return self.register(
            Launchable.operation(
                name,
                arguments=arguments,
                root=root,
                metadata=metadata,
            )
        )

    def recipe(
        self,
        path,
        *,
        arguments=(),
        name=None,
        root=None,
        metadata=None,
    ):
        return self.register(
            Launchable.recipe(
                path,
                arguments=arguments,
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


def _canonical_operation_launchable(runtime, resolution):
    """Return the registered launchable that owns one resolved callable."""
    path = getattr(resolution.callable, "__gway_path__", None)
    if path:
        found = runtime.launchables.resolve(".".join(path))
        if found is not None:
            return found

    candidate = str(resolution.candidate).replace(" ", ".")
    found = runtime.launchables.resolve(candidate)
    if found is not None:
        return found

    operation = getattr(resolution.callable, "__gway_operation__", None)
    subject = getattr(resolution.callable, "__gway_subject__", None)
    for launchable in runtime.launchables.values():
        metadata = launchable.metadata
        if launchable.kind != "operation":
            continue
        if metadata.get("operation") != operation:
            continue
        if metadata.get("subject") != subject:
            continue
        return launchable
    return None


def resolve_launchable(runtime, target):
    """Resolve an operation or recipe invocation without executing it."""
    from .dispatch import resolve_operation
    from .recipes import recipe_path
    from .tokens import token_value, tokenize

    tokens = tokenize(target) if isinstance(target, str) else list(target)
    if not tokens:
        raise ValueError("Service target cannot be empty")

    first = token_value(tokens[0])
    recipe = recipe_path(runtime, first, allow_bare=True)
    if recipe is not None and recipe.is_file():
        return Launchable.recipe(
            recipe,
            arguments=tuple(token_value(item) for item in tokens[1:]),
            metadata={"recipe": str(recipe.resolve())},
        )

    resolution = resolve_operation(runtime, tokens)
    base = _canonical_operation_launchable(runtime, resolution)
    if base is None:
        raise LookupError(
            f"Resolved operation has no launchable: {resolution.candidate}"
        )

    arguments = tuple(token_value(item) for item in resolution.arguments)
    if not arguments:
        return base
    return Launchable.operation(
        base.name,
        arguments=arguments,
        root=base.root,
        metadata=dict(base.metadata),
    )
