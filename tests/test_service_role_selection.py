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


def test_systemctl_permission_words_preserve_called_process_error(monkeypatch) -> None:
    expected = subprocess.CalledProcessError(
        4,
        ["systemctl", "start", "gway-arthexis-web-local.service"],
        output="",
        stderr="Authentication is required to manage system services.",
    )

    def denied(*args, **kwargs):
        raise expected

    monkeypatch.setattr(service.subprocess, "run", denied)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        service._systemctl("start", "gway-arthexis-web-local.service")

    assert exc_info.value is expected


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


def test_explicit_service_install_does_not_reconcile_siblings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = make_role_project(tmp_path)
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    sibling = unit_directory / "gway-arthexis-web-edge.service"
    sibling.write_text("existing sibling", encoding="utf-8")
    manager = service.ServiceManager(
        project,
        service="web-local",
        unit_directory=unit_directory,
    )
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    manager.install(user="arthexis", enable=False, start=False)

    assert sibling.read_text(encoding="utf-8") == "existing sibling"
    assert ("disable", "--now", "gway-arthexis-web-edge.service") not in calls


def test_unmatched_persisted_role_keeps_only_global_services(tmp_path: Path) -> None:
    project = make_role_project(tmp_path)
    manifest_path = project.path / "gway.toml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest = manifest.replace(
        'profiles = ["Terminal", "Watchtower"]',
        'profiles = ["Control"]',
    ).replace(
        'profiles = ["Control", "Watchtower"]',
        'profiles = ["Control"]',
    )
    manifest += '\n[services.health]\ncommand = ["{python}", "-m", "example.health"]\n'
    manifest_path.write_text(manifest, encoding="utf-8")
    (tmp_path / ".locks" / "role.lck").write_text("Terminal\n", encoding="utf-8")

    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    assert manager.active_profile == "Terminal"
    assert manager.unit_names == ["gway-arthexis-health.service"]
