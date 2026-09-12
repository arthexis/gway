from __future__ import annotations

import json
from pathlib import Path

from .config import GwayPaths, default_paths
from .project import ManifestError, Project


class RegistryError(ValueError):
    pass


class Registry:
    def __init__(self, paths: GwayPaths | None = None) -> None:
        self.paths = paths or default_paths()

    def _load_records(self) -> dict[str, dict]:
        path = self.paths.state_file
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"cannot read registry {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RegistryError(f"unsupported registry format in {path}")
        if data.get("version") != 1 or not isinstance(data.get("projects"), dict):
            raise RegistryError(f"unsupported registry format in {path}")
        return data["projects"]

    def _save_records(self, records: dict[str, dict]) -> None:
        path = self.paths.state_file
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "projects": records}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def list(self) -> list[Project]:
        return [Project.from_record(record) for _, record in sorted(self._load_records().items())]

    def get(self, name_or_alias: str) -> Project | None:
        records = self._load_records()
        if name_or_alias in records:
            return Project.from_record(records[name_or_alias])
        for record in records.values():
            if name_or_alias in record.get("aliases", []):
                return Project.from_record(record)
        return None

    def resolve_uninstall(self, name_or_alias: str) -> Project | None:
        project = self.get(name_or_alias)
        if project is not None:
            return project

        for record in self._load_records().values():
            stored = Project.from_record(record)
            try:
                current = Project.from_path(stored.path)
            except (OSError, ManifestError, ValueError):
                continue
            if name_or_alias == current.name or name_or_alias in current.aliases:
                return stored
        return None

    def require(self, name_or_alias: str) -> Project:
        project = self.get(name_or_alias)
        if project is None:
            raise RegistryError(f"project is not registered: {name_or_alias}")
        return project

    def require_uninstall(self, name_or_alias: str) -> Project:
        project = self.resolve_uninstall(name_or_alias)
        if project is None:
            raise RegistryError(f"project is not registered: {name_or_alias}")
        return project

    def unregister(self, name_or_alias: str) -> Project:
        project = self.require_uninstall(name_or_alias)
        records = self._load_records()
        records.pop(project.name, None)
        self._save_records(records)
        return project

    @staticmethod
    def _same_managed_project(existing: Project, project: Project) -> bool:
        if existing.repository and project.repository:
            return existing.repository == project.repository
        return existing.path.resolve() == project.path.resolve()

    def register(self, project: Project) -> Project:
        records = self._load_records()
        claimed = {project.name, *project.aliases}
        if "%" in claimed:
            raise RegistryError("project name or alias is reserved syntax: %")
        if len(claimed) != 1 + len(project.aliases):
            raise RegistryError(f"duplicate name or alias in project {project.name}")

        replaced: set[str] = set()
        for existing_name, record in records.items():
            if existing_name == project.name:
                continue
            existing_claims = {existing_name, *record.get("aliases", [])}
            overlap = claimed & existing_claims
            if not overlap:
                continue
            existing = Project.from_record(record)
            if self._same_managed_project(existing, project):
                replaced.add(existing_name)
                continue
            value = sorted(overlap)[0]
            raise RegistryError(f"project name or alias already registered: {value}")

        for existing_name in replaced:
            records.pop(existing_name, None)
        records[project.name] = project.to_record()
        self._save_records(records)
        return project

    def register_path(self, path: str | Path) -> Project:
        return self.register(Project.from_path(path))
