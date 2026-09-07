from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    adapter_type: str
    adapter_config: dict[str, Any]
    aliases: tuple[str, ...] = ()
    repository: str | None = None
    revision: str | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> Project:
        root = Path(path).expanduser().resolve()
        manifest = root / "gway.toml"
        if not manifest.is_file():
            raise ManifestError(f"missing gway.toml in {root}")

        with manifest.open("rb") as stream:
            data = tomllib.load(stream)

        project_data = data.get("project")
        adapter_data = data.get("adapter")
        if not isinstance(project_data, dict):
            raise ManifestError("gway.toml requires [project]")
        if not isinstance(adapter_data, dict):
            raise ManifestError("gway.toml requires [adapter]")

        name = project_data.get("name")
        adapter_type = adapter_data.get("type")
        if not isinstance(name, str) or not name.strip():
            raise ManifestError("[project].name must be a non-empty string")
        if not isinstance(adapter_type, str) or not adapter_type.strip():
            raise ManifestError("[adapter].type must be a non-empty string")

        aliases_data = project_data.get("aliases", [])
        if not isinstance(aliases_data, list) or not all(
            isinstance(alias, str) and alias for alias in aliases_data
        ):
            raise ManifestError("[project].aliases must be an array of strings")

        adapter_config = dict(adapter_data)
        adapter_config.pop("type", None)

        return cls(
            name=name,
            aliases=tuple(aliases_data),
            path=root,
            adapter_type=adapter_type,
            adapter_config=adapter_config,
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
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> Project:
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            adapter_type=data["adapter_type"],
            adapter_config=dict(data.get("adapter_config", {})),
            aliases=tuple(data.get("aliases", [])),
            repository=data.get("repository"),
            revision=data.get("revision"),
        )
