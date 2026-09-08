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


_HOOK_SCRIPT = """import importlib, json, sys
module_name, function_name = sys.argv[1].split(':', 1)
function = getattr(importlib.import_module(module_name), function_name)
result = function()
if result is not None:
    print(json.dumps(result, default=str))
"""


class Runner:
    """Prepare and refresh isolated environments for managed projects."""

    def __init__(self, paths: GwayPaths | None = None) -> None:
        self.paths = paths or default_paths()

    def environment_path(self, project: Project) -> Path:
        if project.install_layout is not None:
            return project.install_layout.environment
        return self.paths.environments_dir / project.name

    @staticmethod
    def environment_python(environment: Path) -> Path:
        if os.name == "nt":
            return environment / "Scripts" / "python.exe"
        return environment / "bin" / "python"

    def _install_project(self, project: Project, environment: Path, *, upgrade: bool) -> None:
        command = [
            str(self.environment_python(environment)),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
        ]
        if upgrade:
            command.append("--upgrade")
        command.extend(["-e", str(project.path)])
        subprocess.run(command, check=True, stdout=sys.stderr)

    def run_lifecycle(self, project: Project, action: str) -> None:
        hooks = project.lifecycle_hooks
        reference = getattr(hooks, action, None) if hooks is not None else None
        if reference is None:
            return
        environment = project.environment or self.environment_path(project)
        python = self.environment_python(environment)
        if not python.is_file():
            raise RunnerError(f"managed environment is missing Python: {environment}")
        try:
            subprocess.run(
                [str(python), "-c", _HOOK_SCRIPT, reference],
                cwd=project.path,
                check=True,
                stdout=sys.stderr,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(
                f"cannot run {action} lifecycle hook for {project.name}: {exc}"
            ) from exc

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
            self._install_project(project, environment, upgrade=False)
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
            self._install_project(project, environment, upgrade=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(f"cannot refresh environment for {project.name}: {exc}") from exc

        return environment
