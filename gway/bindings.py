"""Generic physical bindings for semantic configuration keys."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .environment import process_environment


class Binding:
    """One optional physical source for a semantic value."""

    def resolve(self):
        raise NotImplementedError


@dataclass(frozen=True)
class EnvironmentBinding(Binding):
    """Resolve one semantic value from a literal environment alias."""

    name: str

    def aliases(self):
        name = str(self.name).strip()
        if not name:
            raise ValueError("environment binding name must be non-empty")
        if name.startswith("GWAY_"):
            return (name,)
        return (f"GWAY_{name}", name)

    def resolve(self):
        for name in self.aliases():
            if name in process_environment:
                return True, process_environment[name]
        return False, None


@dataclass(frozen=True)
class FileBinding(Binding):
    """Resolve one semantic value from an optional text file."""

    path: object

    def resolve(self):
        path = Path(self.path).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError):
            return False, None
        return True, value


class Bindings(Mapping):
    """Semantic-key mapping backed by ordered physical bindings."""

    def __init__(self):
        self._bindings = {}

    def register(self, semantic_key, *bindings, replace=True):
        key = str(semantic_key).strip()
        if not key:
            raise ValueError("semantic binding key must be non-empty")
        if not bindings:
            raise ValueError("at least one physical binding is required")
        normalized = tuple(
            binding if isinstance(binding, Binding) else _coerce_binding(binding)
            for binding in bindings
        )
        if replace or key not in self._bindings:
            self._bindings[key] = normalized
        else:
            self._bindings[key] = (*self._bindings[key], *normalized)
        return self._bindings[key]

    def __getitem__(self, semantic_key):
        bindings = self._bindings[semantic_key]
        for binding in bindings:
            found, value = binding.resolve()
            if found:
                return value
        raise KeyError(semantic_key)

    def __iter__(self):
        return iter(self._bindings)

    def __len__(self):
        return len(self._bindings)


def _coerce_binding(binding):
    if isinstance(binding, tuple) and len(binding) == 2:
        kind, value = binding
        if kind == "env":
            return EnvironmentBinding(value)
        if kind == "file":
            return FileBinding(value)
    raise TypeError("binding must be a Binding or (kind, value) pair")


def env(name):
    """Create one literal environment binding."""
    return EnvironmentBinding(name)


def file(path):
    """Create one optional text-file binding."""
    return FileBinding(path)
