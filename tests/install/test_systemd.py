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
