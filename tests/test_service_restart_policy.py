from gway.gateway import Gateway
from gway.install.systemd import render
from gway.launchable import Launchable
from gway.service.model import Service


def service(tmp_path, **policy):
    launchable = Launchable.operation("demo.worker", root=tmp_path)
    return Service.from_launchable(
        "demo",
        "worker",
        tmp_path,
        launchable,
        **policy,
    )


def test_service_restart_defaults(tmp_path):
    definition = service(tmp_path)

    assert definition.restart == "on-failure"
    assert definition.attempts == 3
    assert definition.restart_sec == 5.0


def test_systemd_renders_default_retry_policy(tmp_path):
    definition = service(tmp_path)

    unit = render(definition, unit="demo-worker.service")

    assert "Restart=on-failure" in unit
    assert "RestartSec=5" in unit
    # Initial launch plus three automatic retries.
    assert "StartLimitBurst=4" in unit
    assert "StartLimitIntervalSec=60" in unit


def test_systemd_renders_service_install_retry_overrides(tmp_path):
    definition = service(
        tmp_path,
        restart="always",
        attempts=7,
        restart_sec=2.0,
    )

    unit = render(definition, unit="demo-worker.service")

    assert "Restart=always" in unit
    assert "RestartSec=2" in unit
    assert "StartLimitBurst=8" in unit


def test_service_attempts_must_be_non_negative(tmp_path):
    launchable = Launchable.operation("demo.worker", root=tmp_path)

    try:
        Service.from_launchable(
            "demo",
            "worker",
            tmp_path,
            launchable,
            attempts=-1,
        )
    except ValueError as exc:
        assert "attempts" in str(exc)
    else:
        raise AssertionError("negative attempts should fail")


def test_service_install_overrides_retry_policy(monkeypatch):
    runtime = Gateway()
    captured = {}

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["project"] = project
            captured["service"] = tuple(services)[0]
            captured["kwargs"] = kwargs
            return ["installed"]

    monkeypatch.setattr("gway.install.backends.get", lambda name: Backend)

    result = runtime._service_controller.install(
        "gway",
        "sous-chef",
        restart="always",
        attempts=6,
        restart_sec=1.5,
    )

    installed = captured["service"]
    assert result == ["installed"]
    assert installed.restart == "always"
    assert installed.attempts == 6
    assert installed.restart_sec == 1.5


def test_process_backend_wraps_command_with_retry_supervisor(tmp_path):
    definition = service(tmp_path)
    command = __import__(
        "gway.service.runtime",
        fromlist=["ProcessBackend"],
    ).ProcessBackend._supervised_command(definition)

    assert command[:4] == [
        command[0],
        "-m",
        "gway.service.supervisor",
        "--restart",
    ]
    assert command[4:10] == [
        "on-failure",
        "--attempts",
        "3",
        "--restart-sec",
        "5.0",
        "--",
    ]
    assert command[-4:] == [
        "-m",
        "gway",
        "demo",
        "worker",
    ]


def test_process_backend_can_disable_retries(tmp_path):
    definition = service(
        tmp_path,
        restart="no",
        attempts=3,
    )
    from gway.service.runtime import ProcessBackend

    assert ProcessBackend._supervised_command(definition) == (
        ProcessBackend._command(definition)
    )
