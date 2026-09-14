from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.project import Project
from gway.service import ServiceError, ServiceManager, systemd


def _project(tmp_path: Path, *, extra: str = "") -> Project:
    root = tmp_path / "managed"
    checkout = root / "app"
    checkout.mkdir(parents=True)
    (checkout / "gway.toml").write_text(
        f"""[project]
name = "demo"

[adapter]
type = "python"
module = "demo"

[install]
root = {str(root)!r}
checkout = "app"
environment = ".venv"

[service]
command = ["{{python}}", "-m", "demo"]
{extra}
""",
        encoding="utf-8",
    )
    return Project.from_path(checkout)


def _completed(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")


def test_managed_services_bound_restart_loops_and_support_on_failure(tmp_path: Path) -> None:
    project = _project(tmp_path, extra='on_failure = ["notify@%n.service"]')

    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(
        user="service-account"
    )

    assert "StartLimitIntervalSec=15min" in rendered
    assert "StartLimitBurst=3" in rendered
    assert "OnFailure=notify@%n.service" in rendered
    assert "Restart=on-failure" in rendered


def test_start_limit_settings_are_configurable_and_validated(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        extra='start_limit_interval_sec = "5min"\nstart_limit_burst = 2',
    )
    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(
        user="service-account"
    )
    assert "StartLimitIntervalSec=5min" in rendered
    assert "StartLimitBurst=2" in rendered

    invalid = _project(
        tmp_path / "invalid",
        extra="start_limit_burst = 0",
    )
    with pytest.raises(ServiceError, match="start_limit_burst must be a positive integer"):
        ServiceManager(invalid, unit_directory=tmp_path / "systemd-invalid").render(
            user="service-account"
        )


def test_start_and_restart_clear_failed_state_first(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(arguments, **_kwargs):
        calls.append(list(arguments))
        return _completed(list(arguments))

    monkeypatch.setattr(systemd.subprocess, "run", run)

    systemd._systemctl("start", "gway-demo.service")
    systemd._systemctl("restart", "gway-demo.service")

    assert calls == [
        ["systemctl", "reset-failed", "gway-demo.service"],
        ["systemctl", "start", "gway-demo.service"],
        ["systemctl", "reset-failed", "gway-demo.service"],
        ["systemctl", "restart", "gway-demo.service"],
    ]


def test_install_clears_failed_state_before_service_restart(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    calls: list[list[str]] = []

    def run(arguments, **_kwargs):
        calls.append(list(arguments))
        return _completed(list(arguments))

    monkeypatch.setattr(systemd.subprocess, "run", run)

    ServiceManager(project, unit_directory=tmp_path / "systemd").install(
        user="service-account"
    )

    reset = ["systemctl", "reset-failed", "gway-demo.service"]
    restart = ["systemctl", "restart", "gway-demo.service"]
    assert reset in calls and restart in calls
    assert calls.index(reset) < calls.index(restart)


def test_unwritable_declared_runtime_path_fails_before_unit_install(
    tmp_path: Path, monkeypatch
) -> None:
    project = _project(tmp_path, extra='writable_paths = ["{project}/runtime"]')
    runtime = project.path / "runtime"
    runtime.mkdir()
    runtime.chmod(0o500)

    assert systemd.pwd is not None
    monkeypatch.setattr(
        systemd.pwd,
        "getpwnam",
        lambda _user: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
    )
    monkeypatch.setattr(systemd.os, "fchown", lambda *_args: None)

    unit_directory = tmp_path / "systemd"
    with pytest.raises(ServiceError, match="cannot write managed runtime path"):
        ServiceManager(project, unit_directory=unit_directory).install(user="service-account")

    assert not unit_directory.exists()
