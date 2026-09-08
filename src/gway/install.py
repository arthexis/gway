from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from .project import Project
from .registry import Registry
from .repository import RepositoryManager, ResolvedRepository
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

    def _place_checkout(
        self,
        checkout: Path,
        project: Project,
        repository: ResolvedRepository,
    ) -> tuple[Path, Project, bool]:
        layout = project.install_layout
        if layout is None or checkout == layout.checkout:
            return checkout, project, False

        target = layout.checkout
        if target.exists():
            self.repositories.validate_checkout(target, repository.full_name)
            existing = Project.from_path(target)
            if existing.name != project.name:
                raise ValueError(
                    f"existing managed checkout has project {existing.name!r}, "
                    f"expected {project.name!r}: {target}"
                )
            if existing.install_layout != project.install_layout:
                message = "existing managed checkout has incompatible install layout"
                raise ValueError(f"{message}: {target}")
            shutil.rmtree(checkout, ignore_errors=True)
            return target, existing, True

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.mkdir()
        except FileExistsError as exc:
            raise ValueError(f"managed checkout appeared during install: {target}") from exc

        try:
            for entry in checkout.iterdir():
                shutil.move(str(entry), str(target / entry.name))
            shutil.copystat(checkout, target, follow_symlinks=False)
            checkout.rmdir()
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return target, replace(project, path=target), False

    def install(self, spec: str) -> Project:
        repository = self.repositories.resolve(spec)
        checkout = self.repositories.clone(repository)
        prepared_environment: Path | None = None
        adopted = False
        environment_preexisted = False
        try:
            project = Project.from_path(checkout)
            checkout, project, adopted = self._place_checkout(checkout, project, repository)
            project = replace(
                project,
                repository=repository.full_name,
                revision=self.repositories.revision(checkout),
            )
            if adopted and project.install_layout is not None:
                environment_preexisted = project.install_layout.environment.exists()
                prepared_environment = self.runner.refresh(project)
            else:
                prepared_environment = self.runner.prepare(project)
            if prepared_environment is not None:
                project = replace(project, environment=prepared_environment)
            if project.lifecycle_hooks is not None:
                self.runner.run_lifecycle(project, "install")
            return self.registry.register(project)
        except Exception:
            if not adopted:
                shutil.rmtree(checkout, ignore_errors=True)
            if prepared_environment is not None and (not adopted or not environment_preexisted):
                shutil.rmtree(prepared_environment, ignore_errors=True)
            raise
