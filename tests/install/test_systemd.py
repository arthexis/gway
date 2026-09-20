import pytest

from gway import Gateway
import gway.install.service.systemd as systemd
from gway.install.service import ServiceInstallState


def test_service_install_systemd_materializes_unit(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    units, calls = fake_systemd

    records = Gateway()("service install --backend systemd sous chef")

    assert (units / "gway-sous-chef.service").is_file()
    assert records[0].service == "sous-chef"
    assert records[0].backend == "systemd"
    assert (("enable", "gway-sous-chef.service"), False, True) in calls

    state = ServiceInstallState(install_environment.data / "services-installed")
    restored = state.get("gway")
    assert [(item.service, item.backend) for item in restored] == [
        ("sous-chef", "systemd")
    ]


def test_service_install_systemd_honors_name_override(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    units, _ = fake_systemd

    records = Gateway()("service install --backend systemd --name scheduler sous chef")

    assert records[0].service == "scheduler"
    assert (units / "gway-scheduler.service").is_file()


def test_service_lifecycle_routes_to_installed_systemd_backend(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    _, calls = fake_systemd
    runtime = Gateway()
    runtime("service install --backend systemd sous chef")

    started = runtime("service start sous chef")
    status = runtime("service status sous chef")
    stopped = runtime("service stop sous chef")

    assert started["running"] is True
    assert status["running"] is True
    assert stopped["running"] is False
    assert (("start", "gway-sous-chef.service"), False, True) in calls
    assert (("stop", "gway-sous-chef.service"), False, False) in calls


def test_unknown_service_backend_fails_without_state(
    tmp_path,
    monkeypatch,
    install_environment,
):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Unsupported service backend"):
        Gateway()("service install --backend unknown sous chef")

    state = ServiceInstallState(install_environment.data / "services-installed")
    assert state.get("gway") == []


def test_systemd_service_install_preserves_other_named_instances(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    units, _ = fake_systemd
    runtime = Gateway()

    runtime("service install --backend systemd --name first sous chef")
    runtime("service install --backend systemd --name second sous chef")

    assert (units / "gway-first.service").is_file()
    assert (units / "gway-second.service").is_file()

    state = ServiceInstallState(install_environment.data / "services-installed")
    assert [(record.service, record.backend) for record in state.get("gway")] == [
        ("first", "systemd"),
        ("second", "systemd"),
    ]


def test_systemd_operation_identity_preserves_scope_options_and_unit():
    reload = systemd._SystemdOperation.from_call(("daemon-reload",), system=False)
    disable = systemd._SystemdOperation.from_call(
        ("disable", "--now", "gway-demo.service"),
        system=True,
    )

    assert reload.action == "daemon-reload"
    assert reload.unit is None
    assert reload.arguments == ()
    assert reload.command == ["systemctl", "--user", "daemon-reload"]

    assert disable.action == "disable"
    assert disable.unit == "gway-demo.service"
    assert disable.arguments == ("--now", "gway-demo.service")
    assert disable.command == [
        "systemctl",
        "disable",
        "--now",
        "gway-demo.service",
    ]


def test_systemctl_reports_progress_with_action_unit_and_scope(monkeypatch, caplog):
    calls = []

    def run(command, **kwargs):
        calls.append((list(command), kwargs))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd.subprocess, "run", run)
    caplog.set_level("INFO", logger="gway")

    systemd._systemctl("daemon-reload", system=False)
    systemd._systemctl("restart", "gway-demo.service", system=True)

    assert calls[0][0] == ["systemctl", "--user", "daemon-reload"]
    assert calls[1][0] == ["systemctl", "restart", "gway-demo.service"]
    messages = [record.getMessage() for record in caplog.records]
    assert "systemd daemon-reload (global) [user]: starting" in messages
    assert "systemd daemon-reload (global) [user]: complete" in messages
    assert "systemd restart gway-demo.service [system]: starting" in messages
    assert "systemd restart gway-demo.service [system]: complete" in messages


def test_systemctl_uses_bounded_default_timeout(monkeypatch):
    captured = {}

    def run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = dict(kwargs)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd.subprocess, "run", run)

    systemd._systemctl("restart", "gway-demo.service", system=True)

    assert captured["command"] == ["systemctl", "restart", "gway-demo.service"]
    assert captured["kwargs"]["timeout"] == systemd.SYSTEMCTL_TIMEOUT
    assert systemd.SYSTEMCTL_TIMEOUT == 40.0


def test_systemctl_timeout_propagates_without_complete_progress(monkeypatch, caplog):
    def run(command, **kwargs):
        raise systemd.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
        )

    monkeypatch.setattr(systemd.subprocess, "run", run)
    caplog.set_level("INFO", logger="gway")

    with pytest.raises(systemd.subprocess.TimeoutExpired) as exc_info:
        systemd._run_systemctl_operation(
            systemd._SystemdOperation.from_call(
                ("restart", "gway-demo.service"),
                system=True,
            ),
            timeout=0.01,
        )

    assert exc_info.value.timeout == 0.01
    messages = [record.getMessage() for record in caplog.records]
    assert "systemd restart gway-demo.service [system]: starting" in messages
    assert "systemd restart gway-demo.service [system]: complete" not in messages
