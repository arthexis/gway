from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gway.service as service
import pytest
from gway.project import Project


MANIFEST = """[project]
name = "epaper"
aliases = ["gway-epaper"]

[adapter]
type = "python"
module = "gway_epaper.commands.main"

[service]
description = "GWAY e-paper display service"
command = ["{python}", "-m", "gway_epaper.service", "{project}/epaper.toml"]
restart = "on-failure"
restart_sec = 5
"""


def make_project(tmp_path: Path) -> Project:
    project_path = tmp_path / "epaper"
    project_path.mkdir()
    (project_path / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    (project_path / "epaper.toml").write_text("[display]\n", encoding="utf-8")
    return Project.from_path(project_path)


def completed(*args: str, returncode: int = 0, stdout: str = ""):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")


def test_project_manifest_preserves_service_metadata(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    assert project.service_config is not None
    assert project.service_config["command"][2] == "gway_epaper.service"

    restored = Project.from_record(project.to_record())
    assert restored.service_config == project.service_config


def test_render_uses_project_manifest_and_expands_placeholders(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    unit = manager.render(user="display")

    assert "Description=GWAY e-paper display service\n" in unit
    expected = (
        f'ExecStart="{sys.executable}" "-m" "gway_epaper.service" '
        f'"{project.path}/epaper.toml"'
    )
    assert expected in unit
    assert "User=display\n" in unit
    assert "Restart=on-failure\n" in unit
    assert "RestartSec=5s\n" in unit
    assert "Wants=network-online.target\n" in unit
    assert "After=network-online.target\n" in unit


def test_manager_reloads_manifest_from_project_path(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    stale = Project(
        name=project.name,
        path=project.path,
        adapter_type=project.adapter_type,
        adapter_config=project.adapter_config,
        service_config={"command": ["stale"]},
    )

    manager = service.ServiceManager(stale, unit_directory=tmp_path / "systemd")
    unit = manager.render(user="display")

    assert "gway_epaper.service" in unit
    assert 'ExecStart="stale"' not in unit


def test_install_and_lifecycle_use_one_project_unit(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append((args, check))
        if args[0] == "is-active":
            return completed(*args, stdout="active\n")
        if args[0] == "is-enabled":
            return completed(*args, stdout="enabled\n")
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    installed = manager.install(user="display")
    assert installed == tmp_path / "systemd" / "gway-epaper.service"
    assert installed.is_file()
    assert (("daemon-reload",), True) in calls
    assert (("enable", "gway-epaper.service"), True) in calls
    assert (("restart", "gway-epaper.service"), True) in calls

    manager.start()
    manager.stop()
    manager.restart()
    status = manager.status()
    assert status["project"] == "epaper"
    assert status["active"] is True
    assert status["enabled"] is True

    assert manager.uninstall() is True
    assert not installed.exists()
    assert (("disable", "--now", "gway-epaper.service"), False) in calls


def test_project_without_service_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / "gway.toml").write_text(
        "[project]\nname = \"plain\"\n[adapter]\ntype = \"python\"\nmodule = \"plain\"\n",
        encoding="utf-8",
    )
    project = Project.from_path(root)

    with pytest.raises(service.ServiceError, match="does not declare"):
        service.ServiceManager(project, unit_directory=tmp_path / "systemd")
