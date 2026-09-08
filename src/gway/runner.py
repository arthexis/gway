from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import GwayPaths, default_paths
from .project import Project


class RunnerError(ValueError):
    pass


class Runner:
    """Prepare and refresh isolated environments for managed projects."""

    def __init__(self, paths: GwayPaths | None = None) -> None:
        self.paths = paths or default_paths()

    def environment_path(self, project: Project) -> Path:
        return project.managed_environment or (self.paths.environments_dir / project.name)

    @staticmethod
    def environment_python(environment: Path) -> Path:
        if os.name == "nt":
            return environment / "Scripts" / "python.exe"
        return environment / "bin" / "python"

    def prepare(self, project: Project) -> Path | None:
        if project.adapter_type not in {"python", "django"}:
            return None

        environment = self.environment_path(project)
        if environment.exists():
            raise RunnerError(f"managed environment already exists: {environment}")
        environment.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(environment)],
                check=True,
                stdout=sys.stderr,
            )
            subprocess.run(
                [
                    str(self.environment_python(environment)),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-e",
                    str(project.path),
                ],
                check=True,
                stdout=sys.stderr,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            shutil.rmtree(environment, ignore_errors=True)
            raise RunnerError(f"cannot prepare environment for {project.name}: {exc}") from exc

        return environment

    def refresh(self, project: Project) -> Path | None:
        """Refresh an existing managed environment after its checkout changes."""
        if project.adapter_type not in {"python", "django"}:
            return None

        environment = project.environment or self.environment_path(project)
        if not environment.exists():
            return self.prepare(project)

        python = self.environment_python(environment)
        if not python.is_file():
            raise RunnerError(f"managed environment is missing Python: {environment}")

        try:
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--upgrade",
                    "-e",
                    str(project.path),
                ],
                check=True,
                stdout=sys.stderr,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(f"cannot refresh environment for {project.name}: {exc}") from exc

        return environment
