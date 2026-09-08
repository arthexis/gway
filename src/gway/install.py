from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from .lifecycle import run_hook
from .project import Project
from .registry import Registry
from .repository import RepositoryManager
from .runner import Runner


class Installer:
    """Coordinate repository checkout, environment setup, and registry state."""

    def __init__(
        self,
        registry: Registry | None = None,
        repositories: RepositoryManager | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.registry = registry or Registry()
        self.repositories = repositories or RepositoryManager(self.registry.paths)
        self.runner = runner or Runner(self.registry.paths)

    @staticmethod
    def _relocate_checkout(project: Project) -> Project:
        destination = project.managed_checkout
        if destination is None or destination.resolve() == project.path.resolve():
            return project
        if destination.exists():
            raise ValueError(f"managed checkout already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(project.path), str(destination))
        return Project.from_path(destination)

    def install(self, spec: str) -> Project:
        repository = self.repositories.resolve(spec)
        checkout = self.repositories.clone(repository)
        managed_checkout = checkout
        prepared_environment: Path | None = None
        try:
            project = Project.from_path(checkout)
            project = self._relocate_checkout(project)
            managed_checkout = project.path
            project = replace(
                project,
                repository=repository.full_name,
                revision=self.repositories.revision(managed_checkout),
            )
            prepared_environment = self.runner.prepare(project)
            if prepared_environment is not None:
                project = replace(project, environment=prepared_environment)
            run_hook(project, "prepare")
            return self.registry.register(project)
        except Exception:
            shutil.rmtree(managed_checkout, ignore_errors=True)
            if checkout != managed_checkout:
                shutil.rmtree(checkout, ignore_errors=True)
            if prepared_environment is not None:
                shutil.rmtree(prepared_environment, ignore_errors=True)
            raise
