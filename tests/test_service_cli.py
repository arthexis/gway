from __future__ import annotations

from pathlib import Path

import pytest

import gway.cli as cli
from gway.cli import main

MANIFEST = """[project]
name = "epaper"
aliases = ["gway-epaper"]

[adapter]
type = "python"
module = "gway_epaper.commands.main"

[service]
command = ["{python}", "-m", "gway_epaper.service", "{project}/epaper.toml"]
"""


def register_project(tmp_path: Path, monkeypatch, capsys) -> Path:
    project = tmp_path / "epaper"
    project.mkdir()
    (project / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_HOME", str(tmp_path / "state"))
    assert main(["register", str(project)]) == 0
    capsys.readouterr()
    return project


def test_service_status_uses_project_flag_and_alias(tmp_path: Path, monkeypatch, capsys) -> None:
    register_project(tmp_path, monkeypatch, capsys)

    def fake_status(self):
        return {
            "project": self.project.name,
            "unit": self.unit_name,
            "active": True,
            "enabled": True,
        }

    monkeypatch.setattr(cli.ServiceManager, "status", fake_status)

    assert main(["service", "status", "--project", "gway-epaper"]) == 0
    output = capsys.readouterr().out
    assert "project: epaper" in output
    assert "unit: gway-epaper.service" in output
    assert "active: true" in output


def test_service_install_forwards_install_options(tmp_path: Path, monkeypatch, capsys) -> None:
    register_project(tmp_path, monkeypatch, capsys)
    captured = {}

    def fake_install(self, *, user=None, enable=True, start=True):
        captured.update(user=user, enable=enable, start=start)
        return Path("/etc/systemd/system") / self.unit_name

    monkeypatch.setattr(cli.ServiceManager, "install", fake_install)

    assert (
        main(
            [
                "service",
                "install",
                "--project",
                "epaper",
                "--user",
                "display",
                "--no-enable",
                "--no-start",
            ]
        )
        == 0
    )
    assert captured == {"user": "display", "enable": False, "start": False}
    assert "status: installed" in capsys.readouterr().out


def test_service_requires_project_selector() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["service", "status"])
    assert exc_info.value.code == 2
