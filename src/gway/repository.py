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
        destination = self.paths.projects_dir / repository.owner / repository.name
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

    @staticmethod
    def _git_failure(result: subprocess.CompletedProcess[str], fallback: str) -> str:
        return result.stderr.strip() or result.stdout.strip() or fallback

    def upgrade(self, checkout: Path, full_name: str, *, force: bool = False) -> str:
        """Upgrade one trusted managed checkout and return its new revision."""
        parts = full_name.split("/")
        if len(parts) != 2 or not all(parts):
            raise RepositoryError(f"invalid managed repository: {full_name}")
        repository = ResolvedRepository(*parts)
        self._validate_owner(repository.owner)

        if not checkout.is_dir():
            raise RepositoryError(f"managed checkout does not exist: {checkout}")

        try:
            status = subprocess.run(
                ["git", "-C", str(checkout), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )

            origin = subprocess.run(
                ["git", "-C", str(checkout), "remote", "get-url", "origin"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if origin.rstrip("/") != repository.clone_url.rstrip("/"):
                raise RepositoryError(
                    f"managed checkout origin does not match registry repository: {checkout}"
                )

            branch = subprocess.run(
                ["git", "-C", str(checkout), "symbolic-ref", "--quiet", "--short", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if not branch:
                raise RepositoryError(f"managed checkout is not on a branch: {checkout}")

            if force:
                fetch = subprocess.run(
                    ["git", "-C", str(checkout), "fetch", "--prune", "origin"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if fetch.returncode != 0:
                    detail = self._git_failure(fetch, "git fetch failed")
                    raise RepositoryError(f"cannot fetch {full_name}: {detail}")

                reset = subprocess.run(
                    ["git", "-C", str(checkout), "reset", "--hard", f"origin/{branch}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if reset.returncode != 0:
                    detail = self._git_failure(reset, "git reset --hard failed")
                    raise RepositoryError(f"cannot reset {full_name}: {detail}")

                clean = subprocess.run(
                    ["git", "-C", str(checkout), "clean", "-fd"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if clean.returncode != 0:
                    detail = self._git_failure(clean, "git clean -fd failed")
                    raise RepositoryError(f"cannot clean {full_name}: {detail}")
            else:
                if status.stdout.strip():
                    raise RepositoryError(
                        f"managed checkout has local changes; refusing upgrade: {checkout}"
                    )

                pull = subprocess.run(
                    ["git", "-C", str(checkout), "pull", "--ff-only"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if pull.returncode != 0:
                    detail = self._git_failure(pull, "git pull --ff-only failed")
                    raise RepositoryError(f"cannot fast-forward {full_name}: {detail}")
        except OSError as exc:
            raise RepositoryError(f"cannot run git: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise RepositoryError(f"cannot validate managed checkout {checkout}: {exc}") from exc

        return self.revision(checkout)
