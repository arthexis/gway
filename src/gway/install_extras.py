from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .project import ManifestError, Project


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
        with manifest.open("rb") as stream:
            data = tomllib.load(stream)
        install = data.get("install")
        if not isinstance(install, dict):
            return None
        config = install.get("extras")
        if config is None:
            return None
        if not isinstance(config, dict):
            raise ManifestError("[install.extras] must be a table")

        argument = config.get("argument")
        default = config.get("default")
        state_value = config.get("state")
        values = config.get("values")
        if not isinstance(argument, str) or not argument.startswith("--"):
            raise ManifestError("[install.extras].argument must be a long option")
        if not isinstance(default, str) or not default.strip():
            raise ManifestError("[install.extras].default must be a non-empty string")
        if not isinstance(state_value, str) or not state_value.strip():
            raise ManifestError("[install.extras].state must be a relative path")
        state = Path(state_value)
        if state.is_absolute() or ".." in state.parts:
            raise ManifestError("[install.extras].state must stay within the project checkout")
        if not isinstance(values, dict) or not values:
            raise ManifestError("[install.extras.values] must declare at least one value")

        normalized_values: dict[str, tuple[str, ...]] = {}
        for key, extras in values.items():
            if not isinstance(key, str) or not key.strip():
                raise ManifestError("[install.extras.values] keys must be non-empty strings")
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
            state=state,
            values=normalized_values,
        )
        selector._canonical(default)
        return selector

    def _canonical(self, value: str) -> str:
        normalized = value.strip().casefold()
        for candidate in self.values:
            if candidate.casefold() == normalized:
                return candidate
        allowed = ", ".join(self.values)
        raise ManifestError(
            f"invalid {self.argument} value {value!r}; expected one of: {allowed}"
        )

    def state_path(self, project: Project) -> Path:
        return project.path / self.state

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

        value = self._canonical(selected or self.current(project) or self.default)
        return InstallExtraSelection(value=value, extras=self.values[value])

    def persist(self, project: Project, value: str) -> None:
        path = self.state_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{self._canonical(value)}\n", encoding="utf-8")

    def snapshot(self, project: Project) -> str | None:
        return self.current(project)

    def restore(self, project: Project, value: str | None) -> None:
        path = self.state_path(project)
        if value is None:
            path.unlink(missing_ok=True)
            return
        self.persist(project, value)
