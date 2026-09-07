from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import GwayConfig, GwayPaths, default_paths, load_config


class RepositoryError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedRepository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.full_name}.git"


class RepositoryManager:
    """Resolve trusted GitHub repositories and manage local checkouts."""

    def __init__(
        self,
        paths: GwayPaths | None = None,
        config: GwayConfig | None = None,
    ) -> None:
        self.paths = paths or default_paths()
        self.config = config or load_config(self.paths)

    def _validate_owner(self, owner: str) -> None:
        if owner not in self.config.trusted_owners:
            raise RepositoryError(f"untrusted GitHub owner: {owner}")

    @staticmethod
    def _exists(repository: ResolvedRepository) -> bool:
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--exit-code", repository.clone_url, "HEAD"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            raise RepositoryError(f"cannot run git: {exc}") from exc
        return result.returncode == 0

    def resolve(self, spec: str) -> ResolvedRepository:
        value = spec.strip()
        if not value:
            raise RepositoryError("repository name must not be empty")

        if "/" in value:
            parts = value.split("/")
            if len(parts) != 2 or not all(parts):
                raise RepositoryError(f"invalid repository name: {spec}")
            owner, name = parts
            self._validate_owner(owner)
            return ResolvedRepository(owner, name)

        for owner in self.config.trusted_owners:
            for name in (f"gway-{value}", value):
                candidate = ResolvedRepository(owner, name)
                if self._exists(candidate):
                    return candidate

        raise RepositoryError(f"cannot resolve GitHub project: {value}")

    def clone(self, repository: ResolvedRepository) -> Path:
        self._validate_owner(repository.owner)
        destination = self.paths.projects_dir / repository.name
        if destination.exists():
            raise RepositoryError(f"managed checkout already exists: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", "--quiet", repository.clone_url, str(destination)],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            shutil.rmtree(destination, ignore_errors=True)
            raise RepositoryError(f"cannot clone {repository.full_name}: {exc}") from exc
        return destination

    @staticmethod
    def revision(checkout: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RepositoryError(f"cannot read revision for {checkout}: {exc}") from exc
        revision = result.stdout.strip()
        if not revision:
            raise RepositoryError(f"empty revision for {checkout}")
        return revision
