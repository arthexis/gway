from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .project import Project


class ServiceError(ValueError):
    pass


_UNIT_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")


def _strings(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ServiceError(f"[service].{field} must be an array of non-empty strings")
    return list(value)


def _service_user(config: dict[str, Any], override: str | None) -> str:
    configured = config.get("user")
    if configured is not None and not isinstance(configured, str):
        raise ServiceError("[service].user must be a string")
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


def _expand(value: str, project: Project) -> str:
    return value.replace("{python}", sys.executable).replace("{project}", str(project.path))


def _service_config(project: Project) -> dict[str, Any]:
    # Reload the manifest so service changes take effect after a managed checkout upgrade
    # without requiring a separate registry refresh operation.
    current = Project.from_path(project.path)
    config = current.service_config
    if config is None:
        raise ServiceError(f"project does not declare [service]: {project.name}")
    return config


def _unit_name(project: Project, config: dict[str, Any]) -> str:
    value = config.get("name", f"gway-{project.name}")
    if not isinstance(value, str) or not value or not _UNIT_NAME.fullmatch(value):
        raise ServiceError("[service].name must be a safe systemd unit name")
    return value if value.endswith(".service") else f"{value}.service"


def _systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *arguments],
        check=check,
        text=True,
        capture_output=True,
    )


class ServiceManager:
    def __init__(self, project: Project, *, unit_directory: str | Path = "/etc/systemd/system"):
        self.project = project
        self.config = _service_config(project)
        self.unit_directory = Path(unit_directory)
        self.unit_name = _unit_name(project, self.config)
        self.unit_path = self.unit_directory / self.unit_name

    def render(self, *, user: str | None = None) -> str:
        command = _strings(self.config.get("command"), "command")
        if not command:
            raise ServiceError("[service].command must contain at least one argument")
        command = [_expand(argument, self.project) for argument in command]

        description = self.config.get("description", f"GWAY {self.project.name} service")
        if not isinstance(description, str) or not description.strip():
            raise ServiceError("[service].description must be a non-empty string")
        if "\n" in description or "\r" in description:
            raise ServiceError("[service].description must not contain newlines")

        wants = _strings(self.config.get("wants", ["network-online.target"]), "wants")
        after = _strings(self.config.get("after", ["network-online.target"]), "after")
        restart = self.config.get("restart", "on-failure")
        restart_sec = self.config.get("restart_sec", 5)
        timeout_stop_sec = self.config.get("timeout_stop_sec", 20)
        if not isinstance(restart, str) or not restart:
            raise ServiceError("[service].restart must be a non-empty string")
        if not isinstance(restart_sec, (int, float)) or restart_sec < 0:
            raise ServiceError("[service].restart_sec must be a non-negative number")
        if not isinstance(timeout_stop_sec, (int, float)) or timeout_stop_sec < 0:
            raise ServiceError("[service].timeout_stop_sec must be a non-negative number")

        environment = self.config.get("environment", {"PYTHONUNBUFFERED": "1"})
        if not isinstance(environment, dict) or not all(
            isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
            for key, value in environment.items()
        ):
            raise ServiceError("[service].environment must be a table of scalar values")

        working_directory = self.config.get("working_directory")
        if working_directory is not None and not isinstance(working_directory, str):
            raise ServiceError("[service].working_directory must be a string")

        lines = ["[Unit]", f"Description={description}"]
        if wants:
            lines.append(f"Wants={' '.join(wants)}")
        if after:
            lines.append(f"After={' '.join(after)}")
        lines.extend(["", "[Service]", "Type=simple", f"User={_service_user(self.config, user)}"])
        if working_directory:
            lines.append(f"WorkingDirectory={_unit_arg(_expand(working_directory, self.project))}")
        for key, value in environment.items():
            lines.append(f"Environment={_unit_arg(f'{key}={value}')}")
        lines.append(f"ExecStart={' '.join(_unit_arg(argument) for argument in command)}")
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

    def install(self, *, user: str | None = None, enable: bool = True, start: bool = True) -> Path:
        self.unit_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.unit_path.with_suffix(self.unit_path.suffix + ".tmp")
        temporary.write_text(self.render(user=user), encoding="utf-8")
        os.replace(temporary, self.unit_path)
        _systemctl("daemon-reload")
        if enable:
            _systemctl("enable", self.unit_name)
        if start:
            _systemctl("restart", self.unit_name)
        return self.unit_path

    def uninstall(self) -> bool:
        existed = self.unit_path.exists()
        _systemctl("disable", "--now", self.unit_name, check=False)
        if existed:
            self.unit_path.unlink()
        _systemctl("daemon-reload")
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
            "unit": self.unit_name,
            "active": active.returncode == 0,
            "active_state": active.stdout.strip() or active.stderr.strip(),
            "enabled": enabled.returncode == 0,
            "enabled_state": enabled.stdout.strip() or enabled.stderr.strip(),
        }
