from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

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

    def install(self, spec: str) -> Project:
        repository = self.repositories.resolve(spec)
        checkout = self.repositories.clone(repository)
        prepared_environment: Path | None = None
        try:
            project = Project.from_path(checkout)
            project = replace(
                project,
                repository=repository.full_name,
                revision=self.repositories.revision(checkout),
            )
            prepared_environment = self.runner.prepare(project)
            if prepared_environment is not None:
                project = replace(project, environment=prepared_environment)
            return self.registry.register(project)
        except Exception:
            shutil.rmtree(checkout, ignore_errors=True)
            if prepared_environment is not None:
                shutil.rmtree(prepared_environment, ignore_errors=True)
            raise
