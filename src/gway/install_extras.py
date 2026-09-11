from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ._toml import tomllib
from .project import ManifestError, Project

_RESERVED_ARGUMENTS = frozenset(
    {
        "--",
        "--all",
        "--force",
        "--help",
        "--interactive",
        "--json",
        "--self",
        "--version",
    }
)


@dataclass(frozen=True)
class InstallExtraSelection:
    value: str
    extras: tuple[str, ...]


@dataclass(frozen=True)
class InstallExtraSelector:
    argument: str
    default: str
    state: Path
    values: dict[str, tuple[str, ...]]

    @classmethod
    def from_project(cls, project: Project) -> InstallExtraSelector | None:
        manifest = project.path / "gway.toml"
        if not manifest.is_file():
            return None
        with manifest.open("rb") as stream:
            data = tomllib.load(stream)

        install = data.get("install")
        if not isinstance(install, dict):
            return None
        extras_config = install.get("extras")
        if extras_config is None:
            return None
        if not isinstance(extras_config, dict):
            raise ManifestError("[install.extras] must be a table")
        return cls._from_install_extras(extras_config)

    @classmethod
    def _from_install_extras(cls, config: dict) -> InstallExtraSelector:
        argument = config.get("argument")
        default = config.get("default")
        state_value = config.get("state")
        values = config.get("values")

        cls._validate_selector_header(argument, default, state_value)
        if not isinstance(values, dict) or not values:
            raise ManifestError("[install.extras.values] must declare at least one value")

        normalized_values: dict[str, tuple[str, ...]] = {}
        canonical_keys: set[str] = set()
        for key, extras in values.items():
            if not isinstance(key, str) or not key.strip():
                raise ManifestError("[install.extras.values] keys must be non-empty strings")
            canonical_key = key.casefold()
            if canonical_key in canonical_keys:
                raise ManifestError("[install.extras.values] keys must be unique ignoring case")
            canonical_keys.add(canonical_key)
            if not isinstance(extras, list) or not all(
                isinstance(extra, str) and extra.strip() for extra in extras
            ):
                raise ManifestError(
                    f"[install.extras.values].{key} must be an array of extra names"
                )
            normalized_values[key] = tuple(extras)

        selector = cls(
            argument=argument,
            default=default,
            state=Path(state_value),
            values=normalized_values,
        )
        selector._canonical(default)
        return selector

    @staticmethod
    def _validate_selector_header(
        argument: object,
        default: object,
        state_value: object,
    ) -> None:
        if (
            not isinstance(argument, str)
            or not argument.startswith("--")
            or argument in _RESERVED_ARGUMENTS
        ):
            raise ManifestError("[install.extras].argument must be a project-owned long option")
        if not isinstance(default, str) or not default.strip():
            raise ManifestError("[install.extras].default must be a non-empty string")
        if not isinstance(state_value, str) or not state_value.strip():
            raise ManifestError("[install.extras].state must be a relative path")
        state = Path(state_value)
        if state.is_absolute() or ".." in state.parts:
            raise ManifestError("[install.extras].state must stay within the install root")

    def _canonical(self, value: str) -> str:
        normalized = value.strip().casefold()
        for candidate in self.values:
            if candidate.casefold() == normalized:
                return candidate
        allowed = ", ".join(self.values)
        raise ManifestError(f"invalid {self.argument} value {value!r}; expected one of: {allowed}")

    def state_path(self, project: Project) -> Path:
        if project.install_layout is None:
            raise ManifestError("[install.extras] requires a managed install layout")
        return project.install_layout.root / self.state

    def current(self, project: Project) -> str | None:
        path = self.state_path(project)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ManifestError(f"cannot read install selector state {path}: {exc}") from exc
        return self._canonical(value) if value else None

    def resolve(
        self,
        project: Project,
        arguments: tuple[str, ...],
    ) -> InstallExtraSelection:
        selected: str | None = None
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument == self.argument:
                if selected is not None:
                    raise ManifestError(f"{self.argument} may only be specified once")
                if index + 1 >= len(arguments):
                    raise ManifestError(f"{self.argument} requires a value")
                selected = arguments[index + 1]
                index += 2
                continue
            if argument.startswith(f"{self.argument}="):
                if selected is not None:
                    raise ManifestError(f"{self.argument} may only be specified once")
                selected = argument.split("=", maxsplit=1)[1]
            index += 1

        if selected is not None:
            value = self._canonical(selected)
        else:
            value = self._canonical(self.current(project) or self.default)
        return InstallExtraSelection(value=value, extras=self.values[value])

    def persist(self, project: Project, value: str) -> None:
        path = self.state_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        canonical = self._canonical(value)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                stream.write(f"{canonical}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def snapshot(self, project: Project) -> str | None:
        return self.current(project)

    def restore(self, project: Project, value: str | None) -> None:
        path = self.state_path(project)
        if value is None:
            path.unlink(missing_ok=True)
            return
        self.persist(project, value)
