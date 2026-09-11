from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._toml import tomllib


class ManifestError(ValueError):
    pass


def _validate_name(name: str) -> None:
    if not name or name != name.strip() or name in {".", ".."}:
        raise ValueError("project name must be a safe directory name")
    if "/" in name or "\\" in name or Path(name).is_absolute():
        raise ValueError("project name must be a safe directory name")
    if name.startswith("["):
        raise ValueError("project name must not start with '['")


def _relative_install_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"[install].{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ManifestError(f"[install].{field} must stay within [install].root")
    return path


_HOOK_REFERENCE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")


def _lifecycle_hook(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _HOOK_REFERENCE.fullmatch(value):
        raise ManifestError(f"[lifecycle].{field} must be a module:function reference")
    return value


@dataclass(frozen=True)
class InstallLayout:
    root: Path
    checkout: Path
    environment: Path

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> InstallLayout:
        root_value = data.get("root")
        if not isinstance(root_value, str) or not root_value.strip():
            raise ManifestError("[install].root must be a non-empty absolute path")
        root = Path(root_value).expanduser()
        if not root.is_absolute():
            raise ManifestError("[install].root must be a non-empty absolute path")

        checkout = _relative_install_path(data.get("checkout"), "checkout")
        environment = _relative_install_path(data.get("environment"), "environment")
        return cls(
            root=root,
            checkout=root / checkout,
            environment=root / environment,
        )

    def to_record(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "checkout": str(self.checkout),
            "environment": str(self.environment),
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> InstallLayout:
        return cls(
            root=Path(data["root"]),
            checkout=Path(data["checkout"]),
            environment=Path(data["environment"]),
        )


@dataclass(frozen=True)
class LifecycleHooks:
    install: str | None = None
    upgrade: str | None = None

    @classmethod
    def from_manifest(cls, data: dict[str, Any]) -> LifecycleHooks:
        install = _lifecycle_hook(data.get("install"), "install")
        upgrade = _lifecycle_hook(data.get("upgrade"), "upgrade")
        if install is None and upgrade is None:
            raise ManifestError("[lifecycle] must declare install and/or upgrade")
        return cls(install=install, upgrade=upgrade)

    def to_record(self) -> dict[str, str | None]:
        return {"install": self.install, "upgrade": self.upgrade}

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> LifecycleHooks:
        return cls(
            install=data.get("install"),
            upgrade=data.get("upgrade"),
        )


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    adapter_type: str
    adapter_config: dict[str, Any]
    aliases: tuple[str, ...] = ()
    alias_arguments: dict[str, tuple[str, ...]] | None = None
    default_command: tuple[str, ...] = ()
    repository: str | None = None
    revision: str | None = None
    environment: Path | None = None
    service_config: dict[str, Any] | None = None
    install_layout: InstallLayout | None = None
    lifecycle_hooks: LifecycleHooks | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name)
        if any(alias.startswith("[") for alias in self.aliases):
            raise ValueError("project aliases must not start with '['")
        if self.alias_arguments is None:
            object.__setattr__(self, "alias_arguments", {})

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
        alias_arguments: dict[str, tuple[str, ...]] = {}
        if isinstance(aliases_data, list):
            if not all(isinstance(alias, str) and alias for alias in aliases_data):
                raise ManifestError("[project].aliases must contain non-empty alias names")
            aliases = tuple(aliases_data)
        elif isinstance(aliases_data, dict):
            if not all(isinstance(alias, str) and alias for alias in aliases_data):
                raise ManifestError("[project].aliases must contain non-empty alias names")
            if not all(
                isinstance(arguments, list)
                and all(isinstance(argument, str) and argument for argument in arguments)
                for arguments in aliases_data.values()
            ):
                raise ManifestError(
                    "[project].aliases values must be arrays of non-empty argument strings"
                )
            aliases = tuple(aliases_data)
            alias_arguments = {alias: tuple(arguments) for alias, arguments in aliases_data.items()}
        else:
            raise ManifestError("[project].aliases must be an array or alias-to-arguments table")
        if any(alias.startswith("[") for alias in aliases):
            raise ManifestError("[project].aliases must not start with '['")

        default_data = project_data.get("default")
        if default_data is None:
            default_command: tuple[str, ...] = ()
        elif isinstance(default_data, str) and default_data.strip():
            default_command = tuple(default_data.split())
        else:
            raise ManifestError("[project].default must be a non-empty command string")

        adapter_config = dict(adapter_data)
        adapter_config.pop("type", None)
        install_layout = (
            InstallLayout.from_manifest(install_data) if install_data is not None else None
        )
        lifecycle_hooks = (
            LifecycleHooks.from_manifest(lifecycle_data) if lifecycle_data is not None else None
        )

        return cls(
            name=name,
            aliases=aliases,
            alias_arguments=alias_arguments,
            default_command=default_command,
            path=root,
            adapter_type=adapter_type,
            adapter_config=adapter_config,
            service_config=dict(service_data) if service_data is not None else None,
            install_layout=install_layout,
            lifecycle_hooks=lifecycle_hooks,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "adapter_type": self.adapter_type,
            "adapter_config": self.adapter_config,
            "aliases": list(self.aliases),
            "alias_arguments": {
                alias: list(arguments) for alias, arguments in (self.alias_arguments or {}).items()
            },
            "default_command": list(self.default_command),
            "repository": self.repository,
            "revision": self.revision,
            "environment": str(self.environment) if self.environment is not None else None,
            "service_config": self.service_config,
            "install_layout": (
                self.install_layout.to_record() if self.install_layout is not None else None
            ),
            "lifecycle_hooks": (
                self.lifecycle_hooks.to_record() if self.lifecycle_hooks is not None else None
            ),
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> Project:
        environment = data.get("environment")
        service_config = data.get("service_config")
        install_layout = data.get("install_layout")
        lifecycle_hooks = data.get("lifecycle_hooks")
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            adapter_type=data["adapter_type"],
            adapter_config=dict(data.get("adapter_config", {})),
            aliases=tuple(data.get("aliases", [])),
            alias_arguments={
                alias: tuple(arguments)
                for alias, arguments in data.get("alias_arguments", {}).items()
            },
            default_command=tuple(data.get("default_command", [])),
            repository=data.get("repository"),
            revision=data.get("revision"),
            environment=Path(environment) if environment else None,
            service_config=dict(service_config) if service_config is not None else None,
            install_layout=(
                InstallLayout.from_record(install_layout)
                if isinstance(install_layout, dict)
                else None
            ),
            lifecycle_hooks=(
                LifecycleHooks.from_record(lifecycle_hooks)
                if isinstance(lifecycle_hooks, dict)
                else None
            ),
        )
