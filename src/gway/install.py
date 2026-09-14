from __future__ import annotations

import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from .config import GwayPaths
from .project import InstallLayout, Project
from .registry import Registry
from .repository import RepositoryManager, ResolvedRepository
from .runner import Runner
from .service import ServiceError, ServiceManager


@dataclass(frozen=True)
class AdoptionPreview:
    """Metadata for a non-destructive managed-install adoption preflight."""

    name: str
    source: Path
    target: Path | None
    revision: str | None


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
        lock = target.with_name(f".{target.name}.gway-install-lock")
        try:
            lock.mkdir()
        except FileExistsError as exc:
            raise ValueError(f"managed checkout install already in progress: {target}") from exc

        temporary: Path | None = None
        try:
            if target.exists():
                raise ValueError(f"managed checkout appeared during install: {target}")

            temporary = Path(
                tempfile.mkdtemp(
                    prefix=f".{target.name}.gway-",
                    dir=target.parent,
                )
            )
            for entry in checkout.iterdir():
                shutil.move(str(entry), str(temporary / entry.name))
            shutil.copystat(checkout, temporary, follow_symlinks=False)
            checkout.rmdir()

            if target.exists():
                raise ValueError(f"managed checkout appeared during install: {target}")
            temporary.rename(target)
            temporary = None
        finally:
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)
            shutil.rmtree(lock, ignore_errors=True)
        return target, replace(project, path=target), False

    @staticmethod
    def _normalized_adoption_arguments(
        arguments: Sequence[str], source: Path
    ) -> tuple[str, ...]:
        normalized: list[str] = []
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument == "--from":
                if index + 1 >= len(arguments):
                    raise ValueError("--from requires PATH")
                normalized.extend(("--from", str(source)))
                index += 2
                continue
            if argument.startswith("--from="):
                normalized.append(f"--from={source}")
                index += 1
                continue
            normalized.append(argument)
            index += 1
        return tuple(normalized)

    def preview_adoption(
        self,
        spec: str,
        source: str | Path,
        *,
        arguments: Sequence[str] = (),
    ) -> AdoptionPreview:
        """Run a project's adoption preflight without creating managed resources."""
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError(f"adoption source is not a directory: {source_path}")
        hook_arguments = self._normalized_adoption_arguments(arguments, source_path)

        repository = self.repositories.resolve(spec)
        with tempfile.TemporaryDirectory(prefix="gway-adopt-") as temporary:
            temporary_root = Path(temporary)
            preview_root = temporary_root / "managed"
            checkout = self.repositories.clone(
                repository,
                destination=preview_root / "app",
            )
            project = Project.from_path(checkout)
            project = replace(
                project,
                repository=repository.full_name,
                revision=self.repositories.revision(checkout),
            )
            target = project.install_layout.checkout if project.install_layout is not None else None

            # Keep the manifest's install semantics available to selectors while
            # remapping every managed path beneath the temporary preview root.
            preview_layout = (
                InstallLayout(
                    root=preview_root,
                    checkout=checkout,
                    environment=preview_root / ".venv",
                )
                if project.install_layout is not None
                else None
            )
            preview_project = replace(project, install_layout=preview_layout)
            preview_runner = Runner(
                GwayPaths(
                    config_dir=temporary_root / "config",
                    data_dir=temporary_root / "data",
                )
            )
            environment = preview_runner.prepare(preview_project, arguments=hook_arguments)
            if environment is not None:
                preview_project = replace(preview_project, environment=environment)
            preview_runner.run_lifecycle(preview_project, "install", hook_arguments)

            return AdoptionPreview(
                name=project.name,
                source=source_path,
                target=target,
                revision=project.revision,
            )

    def install(self, spec: str, *, arguments: Sequence[str] = ()) -> Project:
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
                if arguments:
                    prepared_environment = self.runner.refresh(
                        project,
                        arguments=arguments,
                    )
                else:
                    prepared_environment = self.runner.refresh(project)
            elif arguments:
                prepared_environment = self.runner.prepare(
                    project,
                    arguments=arguments,
                )
            else:
                prepared_environment = self.runner.prepare(project)
            if prepared_environment is not None:
                project = replace(project, environment=prepared_environment)
            if project.lifecycle_hooks is not None:
                if arguments:
                    self.runner.run_lifecycle(project, "install", arguments)
                else:
                    self.runner.run_lifecycle(project, "install")
            return self.registry.register(project)
        except Exception:
            if not adopted:
                shutil.rmtree(checkout, ignore_errors=True)
            if prepared_environment is not None and (not adopted or not environment_preexisted):
                shutil.rmtree(prepared_environment, ignore_errors=True)
            raise

    @staticmethod
    def _uninstall_services(project: Project) -> None:
        try:
            ServiceManager(project, all_services=True).uninstall()
        except ServiceError as exc:
            message = str(exc)
            stale_manifest = "cannot read service manifest" in message
            no_services = "does not declare [service] or [services]" in message
            if not (stale_manifest or no_services):
                raise

    def _can_run_uninstall_hook(self, project: Project, environment: Path) -> bool:
        if not project.path.is_dir() or not environment.is_dir():
            return False
        environment_python = getattr(self.runner, "environment_python", None)
        if callable(environment_python):
            return Path(environment_python(environment)).is_file()
        return True

    def uninstall(self, name_or_alias: str) -> Project:
        project = self.registry.require_uninstall(name_or_alias)

        if project.repository is not None:
            environment = project.environment or self.runner.environment_path(project)

            # Project removal owns the complete service topology, regardless of
            # per-service/profile selectors inherited from the environment.
            self._uninstall_services(project)

            # A stale registration may point at an already-partially-removed
            # checkout/environment. In that case there is no runnable lifecycle
            # hook left, but GWAY must still be able to clear the remaining
            # managed resources and registry record.
            if (
                project.lifecycle_hooks is not None
                and self._can_run_uninstall_hook(project, environment)
            ):
                self.runner.run_lifecycle(project, "uninstall")

            shutil.rmtree(environment, ignore_errors=True)
            shutil.rmtree(project.path, ignore_errors=True)

        return self.registry.unregister(project.name)
