from __future__ import annotations

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


def test_persisted_install_selector_selects_matching_service_profile(tmp_path: Path) -> None:
    project = make_role_project(tmp_path)

    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    assert manager.active_profile == "Watchtower"
    assert manager.unit_names == [
        "gway-arthexis-web-local.service",
        "gway-arthexis-worker.service",
    ]


def test_start_requires_elevation_before_systemctl(tmp_path: Path, monkeypatch) -> None:
    project = make_role_project(tmp_path)
    monkeypatch.setattr(service.os, "geteuid", lambda: 1000)
    manager = service.ServiceManager(project)

    with pytest.raises(service.ServiceError) as exc_info:
        manager.start()

    message = str(exc_info.value)
    assert "requires elevated privileges" in message
    assert "sudo gway service start arthexis" in message


def test_start_reports_missing_units_before_systemctl(tmp_path: Path, monkeypatch) -> None:
    project = make_role_project(tmp_path)
    monkeypatch.setattr(service.os, "geteuid", lambda: 0)
    manager = service.ServiceManager(project)

    with pytest.raises(service.ServiceError) as exc_info:
        manager.start()

    message = str(exc_info.value)
    assert "service unit is not installed" in message
    assert "gway-arthexis-web-local.service" in message
    assert "gway-arthexis-worker.service" in message
    assert "sudo gway service install arthexis" in message
