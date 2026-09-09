from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gway import service
from gway.project import Project


def make_role_project(tmp_path: Path) -> Project:
    root = tmp_path / "app"
    root.mkdir()
    manifest = f'''[project]
name = "arthexis"

[adapter]
type = "python"
module = "example.gway"

[install]
root = "{tmp_path}"
checkout = "app"
environment = ".venv"

[install.extras]
argument = "--role"
default = "Terminal"
state = ".locks/role.lck"

[install.extras.values]
Control = []
Terminal = []
Watchtower = []

[services.web-local]
command = ["{{python}}", "manage.py", "runserver"]
profiles = ["Terminal", "Watchtower"]

[services.web-edge]
command = ["{{python}}", "manage.py", "runserver"]
profiles = ["Control"]

[services.worker]
command = ["{{python}}", "-m", "example.worker"]
profiles = ["Control", "Watchtower"]
'''
    (root / "gway.toml").write_text(manifest, encoding="utf-8")
    role_lock = tmp_path / ".locks" / "role.lck"
    role_lock.parent.mkdir()
    role_lock.write_text("Watchtower\n", encoding="utf-8")
    return Project.from_path(root)


def completed(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_persisted_install_selector_selects_matching_service_profile(tmp_path: Path) -> None:
    project = make_role_project(tmp_path)

    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    assert manager.active_profile == "Watchtower"
    assert manager.unit_names == [
        "gway-arthexis-web-local.service",
        "gway-arthexis-worker.service",
    ]


def test_systemctl_auth_failure_becomes_permission_error(monkeypatch) -> None:
    def denied(*args, **kwargs):
        raise subprocess.CalledProcessError(
            4,
            args[0],
            output="",
            stderr="Authentication is required to manage system services.",
        )

    monkeypatch.setattr(service.subprocess, "run", denied)

    with pytest.raises(PermissionError, match="requires authorization"):
        service._systemctl("start", "gway-arthexis-web-local.service")


def test_start_reports_missing_units_before_systemctl(tmp_path: Path) -> None:
    project = make_role_project(tmp_path)
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    with pytest.raises(service.ServiceError) as exc_info:
        manager.start()

    message = str(exc_info.value)
    assert "service unit is not installed" in message
    assert "gway-arthexis-web-local.service" in message
    assert "gway-arthexis-worker.service" in message
    assert "sudo gway service install arthexis" in message


def test_stop_reaches_systemd_when_unit_files_are_missing(tmp_path: Path, monkeypatch) -> None:
    project = make_role_project(tmp_path)
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    manager.stop()

    assert calls == [
        ("stop", "gway-arthexis-worker.service"),
        ("stop", "gway-arthexis-web-local.service"),
    ]


def test_install_reconciles_units_excluded_by_persisted_role(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = make_role_project(tmp_path)
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    stale = unit_directory / "gway-arthexis-web-edge.service"
    stale.write_text("old Control unit", encoding="utf-8")
    manager = service.ServiceManager(project, unit_directory=unit_directory)
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    manager.install(user="arthexis", enable=False, start=False)

    assert not stale.exists()
    assert ("disable", "--now", "gway-arthexis-web-edge.service") in calls
    assert ("reset-failed", "gway-arthexis-web-edge.service") in calls
    assert calls[-1] == ("daemon-reload",)
