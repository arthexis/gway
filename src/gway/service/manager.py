from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from ..install_extras import InstallExtraSelector
from ..project import Project
from . import systemd
from .manifest import ServiceError, _manifest_services, _strings


class ServiceManager:
    def __init__(self, project: Project, *, service: str | None = None, profile: str | None = None, unit_directory: str | Path = "/etc/systemd/system") -> None:
        self.project = project
        self.unit_directory = Path(unit_directory)
        configs, legacy = _manifest_services(project)
        all_configs = dict(configs)
        environment_service = os.environ.get("GWAY_SERVICE")
        environment_profile = os.environ.get("GWAY_SERVICE_PROFILE")
        self.environment_selectors = [name for name, explicit, value in (("GWAY_SERVICE", service, environment_service), ("GWAY_SERVICE_PROFILE", profile, environment_profile)) if explicit is None and value]
        selected_service = service or environment_service
        active_profile = profile or environment_profile
        if selected_service is None and active_profile is None and not legacy:
            selector = InstallExtraSelector.from_project(project)
            if selector is not None:
                selection = selector.resolve(project, ())
                declared_profiles = {profile_name for key, config in configs.items() for profile_name in _strings(config.get("profiles"), "profiles", f"services.{key}")}
                if declared_profiles:
                    active_profile = selection.value
        if selected_service is not None:
            if selected_service not in configs:
                raise ServiceError(f"project does not declare service {selected_service!r}: {project.name}")
            configs = {selected_service: configs[selected_service]}
        elif active_profile:
            selected: dict[str, dict[str, Any]] = {}
            for key, config in configs.items():
                profiles = _strings(config.get("profiles"), "profiles", f"services.{key}")
                if not profiles or active_profile in profiles:
                    selected[key] = config
            configs = selected
        if not configs:
            raise ServiceError(f"project has no services applicable to profile {active_profile!r}: {project.name}")
        self.active_profile = active_profile
        self._reconcile_topology = selected_service is None and active_profile is not None
        self.units = [systemd._ServiceUnit(project, key, config, legacy=legacy, unit_directory=self.unit_directory, profile=active_profile) for key, config in configs.items()]
        self._all_units = [systemd._ServiceUnit(project, key, config, legacy=legacy, unit_directory=self.unit_directory, profile=active_profile) for key, config in all_configs.items()]
        if len(self.unit_names) != len(set(self.unit_names)):
            raise ServiceError("selected services resolve to duplicate systemd unit names")

    def _sudo_command(self, action: str, *arguments: str) -> str:
        command = ["sudo"]
        if self.environment_selectors:
            command.append(f"--preserve-env={','.join(self.environment_selectors)}")
        command.extend(["gway", "service", action, self.project.name, *arguments])
        return shlex.join(command)

    def _require_installed(self) -> None:
        missing = [unit.unit_name for unit in self.units if not unit.unit_path.is_file()]
        if missing:
            raise ServiceError(f"service unit is not installed: {', '.join(missing)}; run {self._sudo_command('install')}")

    def _reconcile_unselected_units(self) -> None:
        if not self._reconcile_topology:
            return
        selected_names = set(self.unit_names)
        for unit in reversed(self._all_units):
            if unit.unit_name not in selected_names and unit.unit_path.exists():
                unit.uninstall()

    @property
    def unit_names(self) -> list[str]:
        return [unit.unit_name for unit in self.units]

    @property
    def unit_name(self) -> str | list[str]:
        names = self.unit_names
        return names[0] if len(names) == 1 else names

    def render(self, *, user: str | None = None) -> str:
        if len(self.units) != 1:
            raise ServiceError("multiple services selected; choose one service")
        return self.units[0].render(user=user)

    def install(self, *, user: str | None = None, enable: bool = True, start: bool = True) -> Path | list[Path]:
        rendered = [(unit, unit.render(user=user)) for unit in self.units]
        self._reconcile_unselected_units()
        paths = [unit.write(content) for unit, content in rendered]
        systemd._systemctl("daemon-reload")
        if enable:
            for unit in self.units:
                systemd._systemctl("enable", unit.unit_name)
        if start:
            for unit in self.units:
                systemd._systemctl("restart", unit.unit_name)
        return paths[0] if len(paths) == 1 else paths

    def uninstall(self) -> bool | dict[str, bool]:
        removed = {unit.key: unit.uninstall() for unit in reversed(self.units)}
        systemd._systemctl("daemon-reload")
        return next(iter(removed.values())) if len(removed) == 1 else removed

    def start(self) -> None:
        self._require_installed()
        for unit in self.units:
            unit.start()

    def stop(self) -> None:
        for unit in reversed(self.units):
            unit.stop()

    def restart(self) -> None:
        self._require_installed()
        for unit in self.units:
            unit.restart()

    def status(self) -> dict[str, object] | list[dict[str, object]]:
        statuses = [unit.status() for unit in self.units]
        return statuses[0] if len(statuses) == 1 else statuses
