from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import GwayPaths, default_paths
from .install_extras import InstallExtraSelector
from .project import Project


class RunnerError(ValueError):
    pass


_HOOK_SCRIPT = """import importlib, json, sys
module_name, function_name = sys.argv[1].split(':', 1)
function = getattr(importlib.import_module(module_name), function_name)
result = function(*sys.argv[2:])
if result is not None:
    print(json.dumps(result, default=str))
"""
_EXTRAS_MARKER = ".gway-install-extras.json"


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

    @staticmethod
    def _selector(project: Project) -> InstallExtraSelector | None:
        return InstallExtraSelector.from_project(project)

    @staticmethod
    def _extras_marker(environment: Path) -> Path:
        return environment / _EXTRAS_MARKER

    @classmethod
    def _read_managed_extras(cls, environment: Path) -> tuple[str, ...] | None:
        marker = cls._extras_marker(environment)
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise RunnerError(f"cannot read managed extras marker {marker}: {exc}") from exc
        if not isinstance(data, list) or not all(isinstance(value, str) for value in data):
            raise RunnerError(f"invalid managed extras marker: {marker}")
        return tuple(data)

    @classmethod
    def _write_managed_extras(cls, environment: Path, extras: tuple[str, ...]) -> None:
        marker = cls._extras_marker(environment)
        marker.write_text(json.dumps(list(extras)) + "\n", encoding="utf-8")

    def _selection(
        self,
        project: Project,
        arguments: Sequence[str],
    ) -> tuple[InstallExtraSelector | None, str | None, tuple[str, ...]]:
        selector = self._selector(project)
        if selector is None:
            return None, None, ()
        selection = selector.resolve(project, tuple(arguments))
        return selector, selection.value, selection.extras

    @staticmethod
    def _install_spec(project: Project, extras: tuple[str, ...]) -> str:
        path = str(project.path)
        if not extras:
            return path
        return f"{path}[{','.join(extras)}]"

    def _install_project(
        self,
        project: Project,
        environment: Path,
        *,
        upgrade: bool,
        extras: tuple[str, ...] = (),
    ) -> None:
        command = [
            str(self.environment_python(environment)),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
        ]
        if upgrade:
            # Managed checkouts may depend on mutable VCS refs such as @main while
            # keeping the same package version. Force reinstall so refreshing a
            # project also refreshes those dependencies instead of leaving an old
            # resolved commit in the project's environment.
            command.extend(["--upgrade", "--force-reinstall"])
        command.extend(["-e", self._install_spec(project, extras)])
        subprocess.run(command, check=True, stdout=sys.stderr)

    def run_lifecycle(
        self,
        project: Project,
        action: str,
        arguments: Sequence[str] = (),
    ) -> None:
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
                [str(python), "-c", _HOOK_SCRIPT, reference, *arguments],
                cwd=project.path,
                check=True,
                stdout=sys.stderr,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(
                f"cannot run {action} lifecycle hook for {project.name}: {exc}"
            ) from exc

    def prepare(
        self,
        project: Project,
        *,
        arguments: Sequence[str] = (),
    ) -> Path | None:
        if project.adapter_type not in {"python", "django"}:
            return None

        selector, selected_value, extras = self._selection(project, arguments)
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
            self._install_project(project, environment, upgrade=False, extras=extras)
            if selector is not None:
                self._write_managed_extras(environment, extras)
            if selector is not None and selected_value is not None:
                selector.persist(project, selected_value)
        except (OSError, subprocess.CalledProcessError) as exc:
            shutil.rmtree(environment, ignore_errors=True)
            raise RunnerError(f"cannot prepare environment for {project.name}: {exc}") from exc

        return environment

    def refresh(
        self,
        project: Project,
        *,
        arguments: Sequence[str] = (),
    ) -> Path | None:
        """Refresh an existing managed environment after its checkout changes."""
        if project.adapter_type not in {"python", "django"}:
            return None

        selector = self._selector(project)
        selected_value: str | None = None
        extras: tuple[str, ...] = ()
        if selector is not None:
            selection = selector.resolve(project, tuple(arguments))
            selected_value = selection.value
            extras = selection.extras

        environment = project.environment or self.environment_path(project)
        if not environment.exists():
            return self.prepare(project, arguments=arguments)

        python = self.environment_python(environment)
        if not python.is_file():
            raise RunnerError(f"managed environment is missing Python: {environment}")

        managed_extras = self._read_managed_extras(environment)
        if (selector is not None and managed_extras != extras) or (
            selector is None and managed_extras is not None
        ):
            shutil.rmtree(environment)
            return self.prepare(project, arguments=arguments)

        try:
            self._install_project(project, environment, upgrade=True, extras=extras)
            if selector is not None:
                self._write_managed_extras(environment, extras)
            if selector is not None and selected_value is not None:
                selector.persist(project, selected_value)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RunnerError(f"cannot refresh environment for {project.name}: {exc}") from exc

        return environment

    def snapshot_install_selection(self, project: Project) -> str | None:
        selector = self._selector(project)
        return selector.snapshot(project) if selector is not None else None

    def restore_install_selection(self, project: Project, value: str | None) -> None:
        selector = self._selector(project)
        if selector is not None:
            selector.restore(project, value)
