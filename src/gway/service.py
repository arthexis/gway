from __future__ import annotations

import getpass
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from .install_extras import InstallExtraSelector
from .project import Project
from .runner import Runner


class ServiceError(ValueError):
    pass


_UNIT_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")
_SERVICE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")
_SYSTEM_UNIT_DIRECTORY = Path("/etc/systemd/system")


def _strings(value: object, field: str, section: str = "service") -> list[str]:
    valid = isinstance(value, list) and all(isinstance(item, str) and item for item in value)
    if value is None:
        return []
    if not valid:
        message = f"[{section}].{field} must be an array of non-empty strings"
        raise ServiceError(message)
    return list(value)


def _service_user(config: dict[str, Any], override: str | None) -> str:
    configured = config.get("user")
    if configured is not None and not isinstance(configured, str):
        raise ServiceError("service user must be a string")
    value = override or configured or os.environ.get("SUDO_USER") or getpass.getuser()
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ServiceError("service user must be a non-empty account name")
    return value


def _unit_arg(value: str | Path) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ServiceError("systemd arguments must not contain newlines")
    text = text.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _project_python(project: Project) -> str:
    environment = project.environment
    if environment is None and project.install_layout is not None:
        environment = project.install_layout.environment
    if environment is None:
        return sys.executable
    return str(Runner.environment_python(environment))


def _expand(value: str, project: Project) -> str:
    return value.replace("{python}", _project_python(project)).replace(
        "{project}", str(project.path)
    )


def _manifest_services(project: Project) -> tuple[dict[str, dict[str, Any]], bool]:
    manifest = project.path / "gway.toml"
    try:
        with manifest.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ServiceError(f"cannot read service manifest for {project.name}: {exc}") from exc

    legacy = data.get("service")
    services = data.get("services")
    if legacy is not None and services is not None:
        raise ServiceError("gway.toml cannot declare both [service] and [services]")
    if legacy is not None:
        if not isinstance(legacy, dict):
            raise ServiceError("[service] must be a table")
        return {"default": dict(legacy)}, True
    if services is None:
        message = f"project does not declare [service] or [services]: {project.name}"
        raise ServiceError(message)
    if not isinstance(services, dict) or not services:
        raise ServiceError("[services] must contain at least one service table")

    result: dict[str, dict[str, Any]] = {}
    for key, config in services.items():
        if not isinstance(key, str) or not _SERVICE_KEY.fullmatch(key):
            raise ServiceError(f"invalid service key: {key!r}")
        if not isinstance(config, dict):
            raise ServiceError(f"[services.{key}] must be a table")
        result[key] = dict(config)
    return result, False


def _systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *arguments],
        check=check,
        text=True,
        capture_output=True,
    )


class _ServiceUnit:
    def __init__(
        self,
        project: Project,
        key: str,
        config: dict[str, Any],
        *,
        legacy: bool,
        unit_directory: Path,
    ) -> None:
        self.project = project
        self.key = key
        self.config = config
        self.legacy = legacy
        self.unit_directory = unit_directory
        self.unit_name = self._unit_name()
        self.unit_path = unit_directory / self.unit_name

    def _unit_name(self) -> str:
        default = f"gway-{self.project.name}"
        if not self.legacy:
            default = f"{default}-{self.key}"
        value = self.config.get("name", default)
        if not isinstance(value, str) or not value or not _UNIT_NAME.fullmatch(value):
            raise ServiceError("service name must be a safe systemd unit name")
        return value if value.endswith(".service") else f"{value}.service"

    def render(self, *, user: str | None = None) -> str:
        section = "service" if self.legacy else f"services.{self.key}"
        command = _strings(self.config.get("command"), "command", section)
        if not command:
            message = f"[{section}].command must contain at least one argument"
            raise ServiceError(message)
        command = [_expand(argument, self.project) for argument in command]

        if self.legacy:
            default_description = f"GWAY {self.project.name} service"
        else:
            default_description = f"GWAY {self.project.name} {self.key} service"
        description = self.config.get("description", default_description)
        if not isinstance(description, str) or not description.strip():
            raise ServiceError(f"[{section}].description must be a non-empty string")
        if "\n" in description or "\r" in description:
            raise ServiceError(f"[{section}].description must not contain newlines")

        wants = _strings(
            self.config.get("wants", ["network-online.target"]),
            "wants",
            section,
        )
        after = _strings(
            self.config.get("after", ["network-online.target"]),
            "after",
            section,
        )
        requires = _strings(self.config.get("requires"), "requires", section)
        restart = self.config.get("restart", "on-failure")
        restart_sec = self.config.get("restart_sec", 5)
        timeout_stop_sec = self.config.get("timeout_stop_sec", 20)
        if not isinstance(restart, str) or not restart:
            raise ServiceError(f"[{section}].restart must be a non-empty string")
        if not isinstance(restart_sec, (int, float)) or restart_sec < 0:
            raise ServiceError(f"[{section}].restart_sec must be a non-negative number")
        if not isinstance(timeout_stop_sec, (int, float)) or timeout_stop_sec < 0:
            raise ServiceError(f"[{section}].timeout_stop_sec must be a non-negative number")

        environment = self.config.get("environment", {"PYTHONUNBUFFERED": "1"})
        valid_environment = isinstance(environment, dict) and all(
            isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
            for key, value in environment.items()
        )
        if not valid_environment:
            message = f"[{section}].environment must be a table of scalar values"
            raise ServiceError(message)

        working_directory = self.config.get("working_directory")
        if working_directory is not None and not isinstance(working_directory, str):
            raise ServiceError(f"[{section}].working_directory must be a string")

        lines = ["[Unit]", f"Description={description}"]
        if wants:
            lines.append(f"Wants={' '.join(wants)}")
        if requires:
            lines.append(f"Requires={' '.join(requires)}")
        if after:
            lines.append(f"After={' '.join(after)}")
        lines.extend(
            [
                "",
                "[Service]",
                "Type=simple",
                f"User={_service_user(self.config, user)}",
            ]
        )
        if working_directory:
            expanded = _expand(working_directory, self.project)
            lines.append(f"WorkingDirectory={_unit_arg(expanded)}")
        for key, value in environment.items():
            lines.append(f"Environment={_unit_arg(f'{key}={value}')}")
        command_text = " ".join(_unit_arg(argument) for argument in command)
        lines.append(f"ExecStart={command_text}")
        lines.extend(
            [
                f"Restart={restart}",
                f"RestartSec={restart_sec}s",
                f"TimeoutStopSec={timeout_stop_sec}s",
                "",
                "[Install]",
                "WantedBy=multi-user.target",
                "",
            ]
        )
        return "\n".join(lines)

    def write(self, content: str) -> Path:
        self.unit_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.unit_path.with_suffix(self.unit_path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.unit_path)
        return self.unit_path

    def uninstall(self) -> bool:
        existed = self.unit_path.exists()
        _systemctl("disable", "--now", self.unit_name, check=False)
        if existed:
            self.unit_path.unlink()
        _systemctl("reset-failed", self.unit_name, check=False)
        return existed

    def start(self) -> None:
        _systemctl("start", self.unit_name)

    def stop(self) -> None:
        _systemctl("stop", self.unit_name)

    def restart(self) -> None:
        _systemctl("restart", self.unit_name)

    def status(self) -> dict[str, object]:
        active = _systemctl("is-active", self.unit_name, check=False)
        enabled = _systemctl("is-enabled", self.unit_name, check=False)
        return {
            "project": self.project.name,
            "service": self.key,
            "unit": self.unit_name,
            "active": active.returncode == 0,
            "active_state": active.stdout.strip() or active.stderr.strip(),
            "enabled": enabled.returncode == 0,
            "enabled_state": enabled.stdout.strip() or enabled.stderr.strip(),
        }


class ServiceManager:
    def __init__(
        self,
        project: Project,
        *,
        service: str | None = None,
        profile: str | None = None,
        unit_directory: str | Path = "/etc/systemd/system",
    ) -> None:
        self.project = project
        self.unit_directory = Path(unit_directory)
        configs, legacy = _manifest_services(project)
        all_configs = dict(configs)
        environment_service = os.environ.get("GWAY_SERVICE")
        environment_profile = os.environ.get("GWAY_SERVICE_PROFILE")
        self.environment_selectors = [
            name
            for name, explicit, value in (
                ("GWAY_SERVICE", service, environment_service),
                ("GWAY_SERVICE_PROFILE", profile, environment_profile),
            )
            if explicit is None and value
        ]
        selected_service = service or environment_service
        active_profile = profile or environment_profile

        if selected_service is None and active_profile is None and not legacy:
            selector = InstallExtraSelector.from_project(project)
            if selector is not None:
                selection = selector.resolve(project, ())
                declared_profiles = {
                    profile_name
                    for key, config in configs.items()
                    for profile_name in _strings(
                        config.get("profiles"),
                        "profiles",
                        f"services.{key}",
                    )
                }
                if declared_profiles:
                    active_profile = selection.value

        if selected_service is not None:
            if selected_service not in configs:
                message = f"project does not declare service {selected_service!r}: {project.name}"
                raise ServiceError(message)
            configs = {selected_service: configs[selected_service]}
        elif active_profile:
            selected: dict[str, dict[str, Any]] = {}
            for key, config in configs.items():
                profiles = _strings(config.get("profiles"), "profiles", f"services.{key}")
                if not profiles or active_profile in profiles:
                    selected[key] = config
            configs = selected

        if not configs:
            message = (
                f"project has no services applicable to profile {active_profile!r}: {project.name}"
            )
            raise ServiceError(message)
        self.active_profile = active_profile
        self._reconcile_topology = selected_service is None and active_profile is not None
        self.units = [
            _ServiceUnit(
                project,
                key,
                config,
                legacy=legacy,
                unit_directory=self.unit_directory,
            )
            for key, config in configs.items()
        ]
        self._all_units = [
            _ServiceUnit(
                project,
                key,
                config,
                legacy=legacy,
                unit_directory=self.unit_directory,
            )
            for key, config in all_configs.items()
        ]
        unit_names = self.unit_names
        if len(unit_names) != len(set(unit_names)):
            raise ServiceError("selected services resolve to duplicate systemd unit names")

    def _sudo_command(self, action: str, *arguments: str) -> str:
        command = ["sudo"]
        if self.environment_selectors:
            names = ",".join(self.environment_selectors)
            command.append(f"--preserve-env={names}")
        command.extend(["gway", "service", action, self.project.name, *arguments])
        return shlex.join(command)

    def _require_installed(self) -> None:
        missing = [unit.unit_name for unit in self.units if not unit.unit_path.is_file()]
        if not missing:
            return
        names = ", ".join(missing)
        command = self._sudo_command("install")
        raise ServiceError(f"service unit is not installed: {names}; run {command}")

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

    def install(
        self,
        *,
        user: str | None = None,
        enable: bool = True,
        start: bool = True,
    ) -> Path | list[Path]:
        rendered = [(unit, unit.render(user=user)) for unit in self.units]
        self._reconcile_unselected_units()
        paths = [unit.write(content) for unit, content in rendered]
        _systemctl("daemon-reload")
        if enable:
            for unit in self.units:
                _systemctl("enable", unit.unit_name)
        if start:
            for unit in self.units:
                _systemctl("restart", unit.unit_name)
        return paths[0] if len(paths) == 1 else paths

    def uninstall(self) -> bool | dict[str, bool]:
        removed = {unit.key: unit.uninstall() for unit in reversed(self.units)}
        _systemctl("daemon-reload")
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
