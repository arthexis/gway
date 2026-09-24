"""Generic physical bindings for semantic configuration keys."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .environment import process_environment


@dataclass(frozen=True)
class BindingResult:
    """Physical binding resolution with provenance and handling metadata."""

    found: bool
    value: object = None
    sensitive: bool = False
    source: str | None = None


class Binding:
    """One optional physical source for a semantic value."""

    sensitive = False

    def resolve(self):
        raise NotImplementedError


@dataclass(frozen=True)
class EnvironmentBinding(Binding):
    """Resolve one semantic value from a literal environment alias."""

    name: str
    sensitive: bool = False

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
                return BindingResult(
                    True,
                    process_environment[name],
                    sensitive=self.sensitive,
                    source=f"env:{name}",
                )
        return BindingResult(False)


@dataclass(frozen=True)
class FileBinding(Binding):
    """Resolve one semantic value from an optional text file."""

    path: object

    def resolve(self):
        path = Path(self.path).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError):
            return BindingResult(False)
        return BindingResult(True, value, source=f"file:{path}")


@dataclass(frozen=True)
class SecretBinding(Binding):
    """Resolve one value through the configured sensitive-file backend."""

    name: str
    sensitive: bool = True

    def resolve(self):
        from . import secrets

        parts = tuple(part for part in str(self.name).replace("\\", "/").split("/") if part)
        found, value = secrets.read(*parts)
        if not found:
            return BindingResult(False)
        return BindingResult(
            True,
            value,
            sensitive=True,
            source=f"secret:{'/'.join(parts)}",
        )


class Bindings(Mapping):
    """Semantic-key mapping backed by ordered physical bindings."""

    def __init__(self):
        self._bindings = {}
        self._resolved = {}

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
            result = binding.resolve()
            if result.found:
                self._resolved[semantic_key] = result
                return result.value
        self._resolved.pop(semantic_key, None)
        raise KeyError(semantic_key)

    def resolution(self, semantic_key):
        """Return metadata for the latest successful resolution of one key."""
        return self._resolved.get(semantic_key)

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
        if kind == "secret":
            return SecretBinding(value)
    raise TypeError("binding must be a Binding or (kind, value) pair")


def env(name, *, sensitive=False):
    """Create one literal environment binding."""
    return EnvironmentBinding(name, sensitive=bool(sensitive))


def file(path):
    """Create one optional text-file binding."""
    return FileBinding(path)


def secret(name):
    """Create one sensitive binding through the configured secrets backend."""
    return SecretBinding(name)
