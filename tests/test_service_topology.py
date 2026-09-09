from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gway import cli, service
from gway.project import InstallLayout, Project

MULTI_MANIFEST = """[project]
name = "arthexis"

[adapter]
type = "python"
module = "example.gway"

[services.web]
description = "Arthexis web"
command = ["{python}", "manage.py", "runserver"]
working_directory = "{project}"
profiles = ["Control", "Terminal"]
requires = ["postgresql.service"]

[services.worker]
description = "Arthexis worker"
command = ["{python}", "-m", "example.worker"]
profiles = ["Control"]

[services.health]
description = "Arthexis health"
command = ["{python}", "-m", "example.health"]
"""


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "app"
    root.mkdir()
    (root / "gway.toml").write_text(MULTI_MANIFEST, encoding="utf-8")
    environment = tmp_path / ".venv"
    project = Project.from_path(root)
    return Project(
        name=project.name,
        path=project.path,
        adapter_type=project.adapter_type,
        adapter_config=project.adapter_config,
        environment=environment,
        install_layout=InstallLayout(tmp_path, root, environment),
    )


def completed(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="active\n", stderr="")


def test_multi_service_units_use_project_environment_python(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = service.ServiceManager(
        project,
        service="web",
        unit_directory=tmp_path / "systemd",
    )

    unit = manager.render(user="arthexis")

    python = service.Runner.environment_python(project.environment)
    assert manager.unit_name == "gway-arthexis-web.service"
    assert f'ExecStart="{python}" "manage.py" "runserver"' in unit
    assert f'WorkingDirectory="{project.path}"' in unit
    assert "Requires=postgresql.service\n" in unit


def test_profile_selects_matching_and_global_services(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    control = service.ServiceManager(project, profile="Control")
    terminal = service.ServiceManager(project, profile="Terminal")

    assert control.unit_names == [
        "gway-arthexis-web.service",
        "gway-arthexis-worker.service",
        "gway-arthexis-health.service",
    ]
    assert terminal.unit_names == [
        "gway-arthexis-web.service",
        "gway-arthexis-health.service",
    ]


def test_environment_profile_and_service_selectors(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    monkeypatch.setenv("GWAY_SERVICE_PROFILE", "Control")
    monkeypatch.setenv("GWAY_SERVICE", "worker")

    manager = service.ServiceManager(project)

    assert manager.unit_name == "gway-arthexis-worker.service"


def test_install_writes_all_units_before_reload_and_activation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = make_project(tmp_path)
    unit_directory = tmp_path / "systemd"
    manager = service.ServiceManager(project, profile="Terminal", unit_directory=unit_directory)
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        if args[0] == "daemon-reload":
            assert (unit_directory / "gway-arthexis-web.service").is_file()
            assert (unit_directory / "gway-arthexis-health.service").is_file()
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    installed = manager.install(user="arthexis")

    assert isinstance(installed, list)
    assert calls[0] == ("daemon-reload",)
    assert calls[1:3] == [
        ("enable", "gway-arthexis-web.service"),
        ("enable", "gway-arthexis-health.service"),
    ]
    assert calls[3:] == [
        ("restart", "gway-arthexis-web.service"),
        ("restart", "gway-arthexis-health.service"),
    ]


def test_install_validates_every_unit_before_writing(tmp_path: Path) -> None:
    root = tmp_path / "invalid"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "invalid"

[adapter]
type = "python"
module = "example.gway"

[services.first]
command = ["python", "-m", "first"]

[services.second]
command = []
""",
        encoding="utf-8",
    )
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    first_unit = unit_directory / "gway-invalid-first.service"
    first_unit.write_text("old definition", encoding="utf-8")
    manager = service.ServiceManager(Project.from_path(root), unit_directory=unit_directory)

    with pytest.raises(service.ServiceError, match=r"\[services.second\]\.command"):
        manager.install(user="arthexis")

    assert first_unit.read_text(encoding="utf-8") == "old definition"
    assert not (unit_directory / "gway-invalid-second.service").exists()


def test_environment_selector_install_reports_real_permission_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project = make_project(tmp_path)
    monkeypatch.delenv("GWAY_SERVICE", raising=False)
    monkeypatch.setenv("GWAY_SERVICE_PROFILE", "Control")
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    def denied_write(self, content: str):
        raise PermissionError("permission denied while writing service unit")

    monkeypatch.setattr(service._ServiceUnit, "write", denied_write)
    monkeypatch.setattr(cli, "_can_suggest_sudo", lambda: True)

    with pytest.raises(PermissionError) as exc_info:
        manager.install(user="arthexis", enable=False, start=False)

    args = [
        "service",
        "install",
        "arthexis",
        "--user",
        "arthexis",
        "--no-enable",
        "--no-start",
    ]
    assert cli._handle_cli_exception(exc_info.value, args) == 2
    message = capsys.readouterr().err
    assert "permission denied while writing service unit" in message
    assert "sudo gway service install arthexis --user arthexis --no-enable --no-start" in message


def test_environment_selector_uninstall_reports_real_permission_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project = make_project(tmp_path)
    monkeypatch.delenv("GWAY_SERVICE", raising=False)
    monkeypatch.setenv("GWAY_SERVICE_PROFILE", "Control")
    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    def denied_systemctl(*args: str, check: bool = True):
        raise PermissionError("permission denied while managing service")

    monkeypatch.setattr(service, "_systemctl", denied_systemctl)
    monkeypatch.setattr(cli, "_can_suggest_sudo", lambda: True)

    with pytest.raises(PermissionError) as exc_info:
        manager.uninstall()

    args = ["service", "uninstall", "arthexis"]
    assert cli._handle_cli_exception(exc_info.value, args) == 2
    message = capsys.readouterr().err
    assert "permission denied while managing service" in message
    assert "sudo gway service uninstall arthexis" in message


def test_uninstall_stops_units_in_reverse_topology_order(tmp_path: Path, monkeypatch) -> None:
    project = make_project(tmp_path)
    manager = service.ServiceManager(
        project,
        profile="Control",
        unit_directory=tmp_path / "systemd",
    )
    calls: list[tuple[str, ...]] = []

    def fake_systemctl(*args: str, check: bool = True):
        calls.append(args)
        return completed(*args)

    monkeypatch.setattr(service, "_systemctl", fake_systemctl)

    manager.uninstall()

    disables = [args for args in calls if args[:2] == ("disable", "--now")]
    assert disables == [
        ("disable", "--now", "gway-arthexis-health.service"),
        ("disable", "--now", "gway-arthexis-worker.service"),
        ("disable", "--now", "gway-arthexis-web.service"),
    ]


def test_duplicate_resolved_unit_names_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "duplicate"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "duplicate"

[adapter]
type = "python"
module = "example.gway"

[services.one]
name = "shared"
command = ["python", "-m", "one"]

[services.two]
name = "shared.service"
command = ["python", "-m", "two"]
""",
        encoding="utf-8",
    )

    with pytest.raises(service.ServiceError, match="duplicate systemd unit names"):
        service.ServiceManager(Project.from_path(root))


def test_legacy_service_shape_remains_compatible(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "legacy"

[adapter]
type = "python"
module = "legacy"

[service]
command = ["{python}", "-m", "legacy.service"]
""",
        encoding="utf-8",
    )
    project = Project.from_path(root)

    manager = service.ServiceManager(project)
    rendered = manager.render(user="arthexis")

    assert manager.unit_name == "gway-legacy.service"
    assert "Description=GWAY legacy service\n" in rendered
    assert "Description=GWAY legacy default service\n" not in rendered
