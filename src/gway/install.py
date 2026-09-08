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

    @staticmethod
    def _place_checkout(checkout: Path, project: Project) -> tuple[Path, Project]:
        layout = project.install_layout
        if layout is None or checkout == layout.checkout:
            return checkout, project
        if layout.checkout.exists():
            raise ValueError(f"managed checkout already exists: {layout.checkout}")
        layout.checkout.parent.mkdir(parents=True, exist_ok=True)
        placed = Path(shutil.move(str(checkout), str(layout.checkout)))
        return placed, Project.from_path(placed)

    def install(self, spec: str) -> Project:
        repository = self.repositories.resolve(spec)
        checkout = self.repositories.clone(repository)
        prepared_environment: Path | None = None
        try:
            project = Project.from_path(checkout)
            checkout, project = self._place_checkout(checkout, project)
            project = replace(
                project,
                repository=repository.full_name,
                revision=self.repositories.revision(checkout),
            )
            prepared_environment = self.runner.prepare(project)
            if prepared_environment is not None:
                project = replace(project, environment=prepared_environment)
            if project.lifecycle_hooks is not None:
                self.runner.run_lifecycle(project, "install")
            return self.registry.register(project)
        except Exception:
            shutil.rmtree(checkout, ignore_errors=True)
            if prepared_environment is not None:
                shutil.rmtree(prepared_environment, ignore_errors=True)
            raise
