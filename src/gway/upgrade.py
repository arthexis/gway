from __future__ import annotations

import errno
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from .checkout_clean import clean_managed_checkout, split_clean_arguments
from .install import Installer
from .project import Project
from .registry import Registry
from .repository import RepositoryError, RepositoryManager, WorkingTreeEntry
from .runner import Runner
from .upgrade_history import UpgradeHistoryRecord, append_upgrade_history

SELF_SOURCE_SPEC = "git+https://github.com/arthexis/gway.git@main"
logger = logging.getLogger(__name__)


class UpgradeError(ValueError):
    pass


@dataclass(frozen=True)
class UpgradeResult:
    project: Project
    changed: bool
    force_used: bool = False
    force_error_type: str | None = None
    force_error: str | None = None
    dirty_files: tuple[WorkingTreeEntry, ...] = ()
    installed: bool = False


@dataclass(frozen=True)
class RepositoryUpgradeAttempt:
    revision: str
    force_used: bool = False
    force_error_type: str | None = None
    force_error: str | None = None
    dirty_files: tuple[WorkingTreeEntry, ...] = ()


class Upgrader:
    """Upgrade GWAY itself and trusted managed projects."""

    def __init__(
        self,
        registry: Registry | None = None,
        repositories: RepositoryManager | None = None,
        runner: Runner | None = None,
        remote_revision: Callable[[Path, str], str] | None = None,
        checkout_clean: Callable[[Path], bool] | None = None,
    ) -> None:
        self.registry = registry or Registry()
        self.repositories = repositories or RepositoryManager(self.registry.paths)
        self.runner = runner or Runner(self.registry.paths)
        if remote_revision is not None:
            self.remote_revision = remote_revision
        elif repositories is None:
            self.remote_revision = self._remote_revision
        else:
            self.remote_revision = None
        if checkout_clean is not None:
            self.checkout_clean = checkout_clean
        elif repositories is None:
            self.checkout_clean = self._checkout_clean
        else:
            self.checkout_clean = None

    @staticmethod
    def _checkout_clean(checkout: Path) -> bool:
        Runner.configure_managed_checkout(checkout)
        try:
            result = subprocess.run(
                ["git", "-C", str(checkout), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RepositoryError(f"cannot inspect managed checkout {checkout}: {exc}") from exc
        return not result.stdout.strip()

    def _remote_revision(self, checkout: Path, full_name: str) -> str:
        self.repositories.validate_checkout(checkout, full_name)
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            branch = subprocess.run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "symbolic-ref",
                    "--quiet",
                    "--short",
                    "HEAD",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            ).stdout.strip()
            if not branch:
                raise UpgradeError(f"managed checkout is not on a branch: {checkout}")
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(checkout),
                    "ls-remote",
                    "--exit-code",
                    "origin",
                    f"refs/heads/{branch}",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        except OSError as exc:
            raise RepositoryError(f"cannot run git: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise RepositoryError(
                f"cannot read branch for managed checkout {checkout}: {exc}"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "git ls-remote failed"
            raise RepositoryError(f"cannot check remote revision for {full_name}: {detail}")
        revision = result.stdout.split(maxsplit=1)[0] if result.stdout.strip() else ""
        if not revision:
            raise RepositoryError(f"empty remote revision for {full_name}")
        return revision

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

    def _record_force_attempt(
        self,
        *,
        project_name: str,
        repository: str,
        checkout: Path,
        previous_revision: str | None,
        resulting_revision: str | None,
        first_error: RepositoryError,
        succeeded: bool,
        dirty_files: tuple[WorkingTreeEntry, ...],
    ) -> None:
        record = UpgradeHistoryRecord.create(
            project=project_name,
            repository=repository,
            checkout=checkout,
            previous_revision=previous_revision,
            resulting_revision=resulting_revision,
            force_error_type=type(first_error).__name__,
            force_error=str(first_error),
            forced_retry_succeeded=succeeded,
            dirty_files=dirty_files,
        )
        try:
            append_upgrade_history(self.registry.paths, record)
        except PermissionError:
            raise
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EPERM}:
                raise
            try:
                logger.warning("cannot append forced-upgrade history: %s", exc)
            except Exception:
                pass
        except Exception as exc:
            try:
                logger.warning("cannot append forced-upgrade history: %s", exc)
            except Exception:
                pass

    def _upgrade_repository(
        self,
        checkout: Path,
        full_name: str,
        *,
        project_name: str,
        previous_revision: str | None,
        force: bool,
        try_force: bool,
    ) -> RepositoryUpgradeAttempt:
        if force and try_force:
            raise UpgradeError("force and try_force are mutually exclusive")

        if force:
            revision = self.repositories.upgrade(checkout, full_name, force=True)
            return RepositoryUpgradeAttempt(revision=revision, force_used=True)

        try:
            revision = self.repositories.upgrade(checkout, full_name, force=False)
        except RepositoryError as exc:
            if not try_force:
                raise

            actual_previous_revision = self.repositories.revision(checkout)
            force_with_status = getattr(self.repositories, "upgrade_with_status", None)
            dirty_files: tuple[WorkingTreeEntry, ...]
            try:
                if callable(force_with_status):
                    revision, dirty_files = force_with_status(checkout, full_name)
                else:
                    dirty_files = self.repositories.status(checkout)
                    revision = self.repositories.upgrade(checkout, full_name, force=True)
            except RepositoryError as forced_exc:
                self._record_force_attempt(
                    project_name=project_name,
                    repository=full_name,
                    checkout=checkout,
                    previous_revision=actual_previous_revision,
                    resulting_revision=None,
                    first_error=exc,
                    succeeded=False,
                    dirty_files=dirty_files if "dirty_files" in locals() else (),
                )
                raise forced_exc from exc
            self._record_force_attempt(
                project_name=project_name,
                repository=full_name,
                checkout=checkout,
                previous_revision=actual_previous_revision,
                resulting_revision=revision,
                first_error=exc,
                succeeded=True,
                dirty_files=dirty_files,
            )
            return RepositoryUpgradeAttempt(
                revision=revision,
                force_used=True,
                force_error_type=type(exc).__name__,
                force_error=str(exc),
                dirty_files=dirty_files,
            )
        return RepositoryUpgradeAttempt(revision=revision)

    def project_result(
        self,
        name: str,
        *,
        force: bool = False,
        try_force: bool = False,
        reload: bool = False,
        install: bool = False,
        arguments: Sequence[str] = (),
        clean: bool = True,
    ) -> UpgradeResult:
        if force and try_force:
            raise UpgradeError("force and try_force are mutually exclusive")

        install = install or "--install" in arguments
        arguments = tuple(argument for argument in arguments if argument != "--install")
        clean, arguments = split_clean_arguments(arguments, default=clean)

        current = self.registry.get(name)
        if current is None:
            if not install:
                current = self.registry.require(name)
            else:
                project = Installer(
                    self.registry,
                    self.repositories,
                    self.runner,
                ).install(
                    name,
                    arguments=arguments,
                    clean=clean,
                )
                return UpgradeResult(project, changed=True, installed=True)

        if not current.repository:
            raise UpgradeError(
                f"project is locally registered and cannot be upgraded by GWAY: {current.name}"
            )

        previous_revision = current.revision or self.repositories.revision(current.path)
        if clean and not force:
            clean_managed_checkout(current.path, current.repository, self.repositories)

        can_skip = not reload and not arguments and self.remote_revision is not None
        if can_skip and self.checkout_clean is not None:
            can_skip = self.checkout_clean(current.path)
        if can_skip:
            local_revision = self.repositories.revision(current.path)
            remote_revision = self.remote_revision(current.path, current.repository)
            if remote_revision == previous_revision == local_revision:
                return UpgradeResult(current, changed=False)

        selection_snapshot: str | None = None
        selection_captured = False
        snapshot = getattr(self.runner, "snapshot_install_selection", None)
        if callable(snapshot):
            selection_snapshot = snapshot(current)
            selection_captured = True

        attempt = self._upgrade_repository(
            current.path,
            current.repository,
            project_name=current.name,
            previous_revision=previous_revision,
            force=force,
            try_force=try_force,
        )
        revision = attempt.revision
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
            if selection_captured:
                restore = getattr(self.runner, "restore_install_selection", None)
                if callable(restore):
                    try:
                        restore(current, selection_snapshot)
                    except Exception as state_exc:
                        rollback_errors.append(f"selector state restore failed: {state_exc}")

            try:
                self._restore_project(current, previous_revision)
            except Exception as rollback_exc:
                rollback_errors.append(f"checkout rollback failed: {rollback_exc}")

            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise UpgradeError(
                    f"upgrade failed for {current.name} and rollback to {previous_revision} "
                    f"was incomplete: {details}"
                ) from exc
            raise

        assert refreshed is not None
        read_revision = getattr(self.repositories, "revision", None)
        if callable(read_revision):
            revision = read_revision(current.path)
        refreshed = replace(refreshed, revision=revision)
        registered = self.registry.register(refreshed)
        return UpgradeResult(
            registered,
            changed=True,
            force_used=attempt.force_used,
            force_error_type=attempt.force_error_type,
            force_error=attempt.force_error,
            dirty_files=attempt.dirty_files,
        )

    def project(
        self,
        name: str,
        *,
        force: bool = False,
        try_force: bool = False,
        reload: bool = False,
        install: bool = False,
        arguments: Sequence[str] = (),
        clean: bool = True,
    ) -> Project:
        return self.project_result(
            name,
            force=force,
            try_force=try_force,
            reload=reload,
            install=install,
            arguments=arguments,
            clean=clean,
        ).project

    def all_project_results(
        self,
        *,
        force: bool = False,
        try_force: bool = False,
        reload: bool = False,
        clean: bool = True,
    ) -> list[UpgradeResult]:
        if force and try_force:
            raise UpgradeError("force and try_force are mutually exclusive")
        results: list[UpgradeResult] = []
        for project in self.registry.list():
            if project.repository is None:
                continue
            results.append(
                self.project_result(
                    project.name,
                    force=force,
                    try_force=try_force,
                    reload=reload,
                    clean=clean,
                )
            )
        return results

    def all_projects(
        self,
        *,
        force: bool = False,
        try_force: bool = False,
        reload: bool = False,
        clean: bool = True,
    ) -> list[Project]:
        return [
            result.project
            for result in self.all_project_results(
                force=force,
                try_force=try_force,
                reload=reload,
                clean=clean,
            )
        ]

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
