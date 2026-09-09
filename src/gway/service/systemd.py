from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..project import Project
from ..runner import Runner
from .manifest import ServiceError, _strings

_UNIT_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")


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


def _unit_path(value: str | Path, field: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ServiceError(f"{field} must not contain newlines")
    if not Path(text).is_absolute():
        raise ServiceError(f"{field} must expand to an absolute path")
    return text


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
            lines.append(
                f"WorkingDirectory={_unit_path(expanded, f'[{section}].working_directory')}"
            )
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
