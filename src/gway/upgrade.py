from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
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

    def _restore_project(self, current: Project, revision: str) -> None:
        assert current.repository is not None
        self.repositories.reset(current.path, current.repository, revision)
        restored = Project.from_path(current.path)
        restored = replace(
            restored,
            repository=current.repository,
            revision=revision,
            environment=current.environment,
        )
        self.runner.refresh(restored)

    def project(
        self,
        name: str,
        *,
        force: bool = False,
        arguments: Sequence[str] = (),
    ) -> Project:
        current = self.registry.require(name)
        if not current.repository:
            raise UpgradeError(
                f"project is locally registered and cannot be upgraded by GWAY: {current.name}"
            )

        selection_snapshot: str | None = None
        selection_captured = False
        snapshot = getattr(self.runner, "snapshot_install_selection", None)
        if callable(snapshot):
            selection_snapshot = snapshot(current)
            selection_captured = True

        previous_revision = current.revision or self.repositories.revision(current.path)
        revision = self.repositories.upgrade(
            current.path,
            current.repository,
            force=force,
        )
        refreshed: Project | None = None
        try:
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
            if arguments:
                environment = self.runner.refresh(
                    refreshed,
                    arguments=arguments,
                )
            else:
                environment = self.runner.refresh(refreshed)
            if environment is not None:
                refreshed = replace(refreshed, environment=environment)
            if refreshed.lifecycle_hooks is not None:
                if arguments:
                    self.runner.run_lifecycle(refreshed, "upgrade", arguments)
                else:
                    self.runner.run_lifecycle(refreshed, "upgrade")
        except Exception as exc:
            rollback_errors: list[str] = []
            try:
                self._restore_project(current, previous_revision)
            except Exception as rollback_exc:
                rollback_errors.append(f"checkout rollback failed: {rollback_exc}")

            if selection_captured:
                restore = getattr(self.runner, "restore_install_selection", None)
                if callable(restore):
                    try:
                        restore(current, selection_snapshot)
                    except Exception as state_exc:
                        rollback_errors.append(f"selector state restore failed: {state_exc}")

            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise UpgradeError(
                    f"upgrade failed for {current.name} and rollback to {previous_revision} "
                    f"was incomplete: {details}"
                ) from exc
            raise

        assert refreshed is not None
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
                stdout=sys.stderr,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise UpgradeError(f"cannot upgrade GWAY itself: {exc}") from exc
