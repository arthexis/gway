from __future__ import annotations

import subprocess
from pathlib import Path

from gway import service
from gway.project import Project


def _completed(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "arthexis"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "arthexis"

[adapter]
type = "python"
module = "example.gway"

[services.web-local]
command = ["python", "-m", "example.web"]

[services.worker]
command = ["python", "-m", "example.worker"]
""",
        encoding="utf-8",
    )
    return Project.from_path(root)


def test_install_removes_obsolete_default_named_project_units(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    obsolete = unit_directory / "gway-arthexis-web-edge.service"
    obsolete.write_text("old", encoding="utf-8")
    unrelated = unit_directory / "gway-other-web-edge.service"
    unrelated.write_text("other", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return _completed(*args)

    monkeypatch.setattr(service.systemd, "_systemctl", fake_systemctl)

    manager = service.ServiceManager(project, unit_directory=unit_directory)
    manager.install(user="arthexis", enable=False, start=False)

    assert not obsolete.exists()
    assert unrelated.is_file()
    assert ("disable", "--now", "gway-arthexis-web-edge.service") in calls
    assert ("reset-failed", "gway-arthexis-web-edge.service") in calls
    assert calls[-1] == ("daemon-reload",)


def test_profile_install_keeps_declared_units_outside_selected_profile(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "profiled"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "profiled"

[adapter]
type = "python"
module = "example.gway"

[services.web]
command = ["python", "-m", "example.web"]
profiles = ["Terminal"]

[services.worker]
command = ["python", "-m", "example.worker"]
profiles = ["Control"]
""",
        encoding="utf-8",
    )
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    worker = unit_directory / "gway-profiled-worker.service"
    worker.write_text("existing Control unit", encoding="utf-8")

    monkeypatch.setattr(
        service.systemd,
        "_systemctl",
        lambda *args, check=True: _completed(*args),
    )

    manager = service.ServiceManager(
        Project.from_path(root),
        profile="Terminal",
        unit_directory=unit_directory,
    )
    manager.install(user="arthexis", enable=False, start=False)

    assert worker.is_file()
