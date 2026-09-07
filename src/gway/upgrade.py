from __future__ import annotations

import subprocess
import sys
from dataclasses import replace

from .project import Project
from .registry import Registry
from .repository import RepositoryManager
from .runner import Runner

SELF_SOURCE_SPEC = "git+https://github.com/arthexis/gway.git@main"


class UpgradeError(ValueError):
    pass


class Upgrader:
    """Upgrade GWAY itself and trusted managed projects."""

    def __init__(
        self,
        registry: Registry | None = None,
        repositories: RepositoryManager | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.registry = registry or Registry()
        self.repositories = repositories or RepositoryManager(self.registry.paths)
        self.runner = runner or Runner(self.registry.paths)

    def project(self, name: str, *, force: bool = False) -> Project:
        current = self.registry.require(name)
        if not current.repository:
            raise UpgradeError(
                f"project is locally registered and cannot be upgraded by GWAY: {current.name}"
            )

        revision = self.repositories.upgrade(
            current.path,
            current.repository,
            force=force,
        )
        refreshed = Project.from_path(current.path)
        if refreshed.name != current.name:
            raise UpgradeError(
                f"managed project changed name from {current.name!r} to {refreshed.name!r}; "
                "refusing upgrade"
            )

        refreshed = replace(
            refreshed,
            repository=current.repository,
            revision=revision,
            environment=current.environment,
        )
        environment = self.runner.refresh(refreshed)
        if environment is not None:
            refreshed = replace(refreshed, environment=environment)
        return self.registry.register(refreshed)

    def all_projects(self, *, force: bool = False) -> list[Project]:
        upgraded: list[Project] = []
        for project in self.registry.list():
            if project.repository is None:
                continue
            upgraded.append(self.project(project.name, force=force))
        return upgraded

    @staticmethod
    def upgrade_self(source_spec: str = SELF_SOURCE_SPEC) -> None:
        """Upgrade GWAY in the Python environment executing this command."""
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--upgrade",
                    "--force-reinstall",
                    source_spec,
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise UpgradeError(f"cannot upgrade GWAY itself: {exc}") from exc
