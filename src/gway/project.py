from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


def _validate_name(name: str) -> None:
    if not name or name != name.strip() or name in {".", ".."}:
        raise ValueError("project name must be a safe directory name")
    if "/" in name or "\\" in name or Path(name).is_absolute():
        raise ValueError("project name must be a safe directory name")


def _validate_relative_component(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ManifestError(f"{field} must be a safe relative path")
    return value


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    adapter_type: str
    adapter_config: dict[str, Any]
    aliases: tuple[str, ...] = ()
    repository: str | None = None
    revision: str | None = None
    environment: Path | None = None
    service_config: dict[str, Any] | None = None
    install_config: dict[str, Any] | None = None
    lifecycle_config: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name)

    @property
    def managed_root(self) -> Path | None:
        if self.install_config is None:
            return None
        root = self.install_config.get("root")
        if root is None:
            return None
        return Path(str(root)).expanduser()

    @property
    def managed_checkout(self) -> Path | None:
        root = self.managed_root
        if root is None:
            return None
        checkout = str((self.install_config or {}).get("checkout", self.name))
        return root / checkout

    @property
    def managed_environment(self) -> Path | None:
        root = self.managed_root
        if root is None:
            return None
        environment = str((self.install_config or {}).get("environment", ".venv"))
        return root / environment

    @classmethod
    def from_path(cls, path: str | Path) -> Project:
        root = Path(path).expanduser().resolve()
        manifest = root / "gway.toml"
        if not manifest.is_file():
            raise ManifestError(f"missing gway.toml in {root}")

        try:
            with manifest.open("rb") as stream:
                data = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exc:
            raise ManifestError(f"invalid gway.toml in {root}: {exc}") from exc

        project_data = data.get("project")
        adapter_data = data.get("adapter")
        service_data = data.get("service")
        install_data = data.get("install")
        lifecycle_data = data.get("lifecycle")
        if not isinstance(project_data, dict):
            raise ManifestError("gway.toml requires [project]")
        if not isinstance(adapter_data, dict):
            raise ManifestError("gway.toml requires [adapter]")
        if service_data is not None and not isinstance(service_data, dict):
            raise ManifestError("[service] must be a table")
        if install_data is not None and not isinstance(install_data, dict):
            raise ManifestError("[install] must be a table")
        if lifecycle_data is not None and not isinstance(lifecycle_data, dict):
            raise ManifestError("[lifecycle] must be a table")

        name = project_data.get("name")
        adapter_type = adapter_data.get("type")
        if not isinstance(name, str) or not name.strip():
            raise ManifestError("[project].name must be a non-empty string")
        try:
            _validate_name(name)
        except ValueError as exc:
            raise ManifestError("[project].name must be a safe directory name") from exc
        if not isinstance(adapter_type, str) or not adapter_type.strip():
            raise ManifestError("[adapter].type must be a non-empty string")

        aliases_data = project_data.get("aliases", [])
        if not isinstance(aliases_data, list) or not all(
            isinstance(alias, str) and alias for alias in aliases_data
        ):
            raise ManifestError("[project].aliases must be an array of strings")

        if install_data is not None:
            install_root = install_data.get("root")
            if not isinstance(install_root, str) or not install_root.strip():
                raise ManifestError("[install].root must be a non-empty path")
            _validate_relative_component(install_data.get("checkout", name), "[install].checkout")
            _validate_relative_component(
                install_data.get("environment", ".venv"), "[install].environment"
            )

        if lifecycle_data is not None:
            for key, value in lifecycle_data.items():
                if not isinstance(value, str) or not value.strip():
                    raise ManifestError(f"[lifecycle].{key} must be a non-empty command name")

        adapter_config = dict(adapter_data)
        adapter_config.pop("type", None)

        return cls(
            name=name,
            aliases=tuple(aliases_data),
            path=root,
            adapter_type=adapter_type,
            adapter_config=adapter_config,
            service_config=dict(service_data) if service_data is not None else None,
            install_config=dict(install_data) if install_data is not None else None,
            lifecycle_config=(
                dict(lifecycle_data) if lifecycle_data is not None else None
            ),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "adapter_type": self.adapter_type,
            "adapter_config": self.adapter_config,
            "aliases": list(self.aliases),
            "repository": self.repository,
            "revision": self.revision,
            "environment": str(self.environment) if self.environment is not None else None,
            "service_config": self.service_config,
            "install_config": self.install_config,
            "lifecycle_config": self.lifecycle_config,
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> Project:
        environment = data.get("environment")
        service_config = data.get("service_config")
        install_config = data.get("install_config")
        lifecycle_config = data.get("lifecycle_config")
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            adapter_type=data["adapter_type"],
            adapter_config=dict(data.get("adapter_config", {})),
            aliases=tuple(data.get("aliases", [])),
            repository=data.get("repository"),
            revision=data.get("revision"),
            environment=Path(environment) if environment else None,
            service_config=dict(service_config) if service_config is not None else None,
            install_config=dict(install_config) if install_config is not None else None,
            lifecycle_config=(
                dict(lifecycle_config) if lifecycle_config is not None else None
            ),
        )
