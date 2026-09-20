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
