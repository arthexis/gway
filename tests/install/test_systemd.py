import pytest

import gway.install.service.systemd as systemd
from gway import Gateway
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


def test_service_install_timeout_flag_reaches_each_systemd_operation(
    tmp_path,
    monkeypatch,
    install_environment,
    record_systemd_operations,
):
    monkeypatch.chdir(tmp_path)
    units = tmp_path / "units"
    monkeypatch.setattr(systemd, "unit_root", lambda **kwargs: units)

    Gateway()("service install --backend systemd --timeout 55 sous chef")

    assert ("daemon-reload", None, True, 55.0) in record_systemd_operations
    assert (
        "enable",
        "gway-sous-chef.service",
        True,
        55.0,
    ) in record_systemd_operations


def test_service_runtime_timeout_flag_reaches_action_and_status_probe(
    tmp_path,
    monkeypatch,
    install_environment,
    record_systemd_operations,
):
    monkeypatch.chdir(tmp_path)
    units = tmp_path / "units"
    monkeypatch.setattr(systemd, "unit_root", lambda **kwargs: units)

    runtime = Gateway()
    runtime("service install --backend systemd sous chef")
    record_systemd_operations.clear()

    runtime("service restart --timeout 65 sous chef")

    assert record_systemd_operations == [
        ("restart", "gway-sous-chef.service", True, 65.0),
        ("is-active", "gway-sous-chef.service", False, 65.0),
    ]


def test_checked_systemctl_failure_raises_structured_operation_error(monkeypatch, caplog):
    def run(command, **kwargs):
        raise systemd.subprocess.CalledProcessError(
            5,
            command,
            output="unit output",
            stderr="permission denied",
        )

    monkeypatch.setattr(systemd.subprocess, "run", run)
    caplog.set_level("INFO", logger="gway")

    operation = systemd._SystemdOperation.from_call(
        ("enable", "gway-demo.service"),
        system=True,
    )
    with pytest.raises(systemd._SystemdOperationError) as exc_info:
        systemd._run_systemctl_operation(operation, check=True)

    error = exc_info.value
    assert error.action == "enable"
    assert error.unit == "gway-demo.service"
    assert error.system is True
    assert error.returncode == 5
    assert error.timeout is None
    assert error.stdout == "unit output"
    assert error.stderr == "permission denied"
    assert "action=enable" in str(error)
    assert "scope=system" in str(error)
    assert "exit=5" in str(error)
    assert "permission denied" in str(error)
    assert isinstance(error.__cause__, systemd.subprocess.CalledProcessError)

    messages = [record.getMessage() for record in caplog.records]
    assert "systemd enable gway-demo.service [system]: starting" in messages
    assert "systemd enable gway-demo.service [system]: failed with exit 5" in messages
    assert "systemd enable gway-demo.service [system]: complete" not in messages


def test_systemctl_timeout_raises_structured_operation_error(monkeypatch, caplog):
    def run(command, **kwargs):
        raise systemd.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output=b"partial output",
            stderr=b"still waiting",
        )

    monkeypatch.setattr(systemd.subprocess, "run", run)
    caplog.set_level("INFO", logger="gway")

    operation = systemd._SystemdOperation.from_call(
        ("restart", "gway-demo.service"),
        system=True,
    )
    with pytest.raises(systemd._SystemdOperationError) as exc_info:
        systemd._run_systemctl_operation(operation, timeout=0.01)

    error = exc_info.value
    assert error.action == "restart"
    assert error.unit == "gway-demo.service"
    assert error.system is True
    assert error.returncode is None
    assert error.timeout == 0.01
    assert error.stdout == "partial output"
    assert error.stderr == "still waiting"
    assert "timed out after 0.01s" in str(error)
    assert "still waiting" in str(error)
    assert isinstance(error.__cause__, systemd.subprocess.TimeoutExpired)

    messages = [record.getMessage() for record in caplog.records]
    assert "systemd restart gway-demo.service [system]: starting" in messages
    assert "systemd restart gway-demo.service [system]: timed out after 0.01s" in messages
    assert "systemd restart gway-demo.service [system]: complete" not in messages


def test_check_false_preserves_nonzero_result(monkeypatch):
    def run(command, **kwargs):
        return systemd.subprocess.CompletedProcess(
            command,
            3,
            stdout="inactive",
            stderr="",
        )

    monkeypatch.setattr(systemd.subprocess, "run", run)

    result = systemd._run_systemctl_operation(
        systemd._SystemdOperation.from_call(
            ("is-active", "gway-demo.service"),
            system=False,
        ),
        check=False,
    )

    assert result.returncode == 3
    assert result.stdout == "inactive"


def test_check_false_timeout_still_raises_structured_operation_error(monkeypatch):
    def run(command, **kwargs):
        raise systemd.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(systemd.subprocess, "run", run)

    with pytest.raises(systemd._SystemdOperationError) as exc_info:
        systemd._run_systemctl_operation(
            systemd._SystemdOperation.from_call(
                ("stop", "gway-demo.service"),
                system=False,
            ),
            check=False,
            timeout=0.01,
        )

    assert exc_info.value.timeout == 0.01
    assert exc_info.value.action == "stop"


def test_systemd_diagnostics_are_bounded():
    text = "x" * 5000

    rendered = systemd._diagnostic_text(text)

    assert rendered.endswith("...<truncated>")
    assert len(rendered) < len(text)


def _named_sous_services(*names):
    runtime = Gateway()
    return [
        runtime._service_controller._definition(("sous", "chef"), name=name)
        for name in names
    ]


def test_systemd_install_reconciliation_runs_forward_operations_in_order(
    tmp_path,
    record_systemd_operations,
):
    services = _named_sous_services("web", "worker", "beat")

    systemd.install_units(
        "gway",
        services,
        state_root=tmp_path / "state",
        root=tmp_path / "units",
        timeout=55,
    )

    assert record_systemd_operations == [
        ("daemon-reload", None, True, 55),
        ("enable", "gway-web.service", True, 55),
        ("enable", "gway-worker.service", True, 55),
        ("enable", "gway-beat.service", True, 55),
    ]


def test_checked_failure_aborts_later_forward_systemd_operations(
    tmp_path,
    monkeypatch,
):
    observed = []
    services = _named_sous_services("web", "worker", "beat")

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        observed.append((operation.action, operation.unit, check, timeout))
        if (
            operation.action == "enable"
            and operation.unit == "gway-worker.service"
            and check
        ):
            raise systemd._SystemdOperationError(
                operation,
                "worker enable failed",
                returncode=1,
                stderr="boom",
            )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)

    with pytest.raises(systemd._SystemdOperationError) as exc_info:
        systemd.install_units(
            "gway",
            services,
            state_root=tmp_path / "state",
            root=tmp_path / "units",
            timeout=40,
        )

    assert exc_info.value.unit == "gway-worker.service"
    forward = [(action, unit) for action, unit, check, _ in observed if check]
    assert forward == [
        ("daemon-reload", None),
        ("enable", "gway-web.service"),
        ("enable", "gway-worker.service"),
    ]
    assert ("enable", "gway-beat.service") not in forward


def test_timeout_aborts_later_forward_systemd_operations(
    tmp_path,
    monkeypatch,
):
    observed = []
    services = _named_sous_services("web", "worker", "beat")

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        observed.append((operation.action, operation.unit, check, timeout))
        if (
            operation.action == "enable"
            and operation.unit == "gway-worker.service"
            and check
        ):
            raise systemd._SystemdOperationError(
                operation,
                "worker enable timed out",
                timeout=timeout,
            )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)

    with pytest.raises(systemd._SystemdOperationError) as exc_info:
        systemd.install_units(
            "gway",
            services,
            state_root=tmp_path / "state",
            root=tmp_path / "units",
            timeout=77,
        )

    assert exc_info.value.timeout == 77
    forward = [
        (action, unit, timeout)
        for action, unit, check, timeout in observed
        if check
    ]
    assert forward == [
        ("daemon-reload", None, 77),
        ("enable", "gway-web.service", 77),
        ("enable", "gway-worker.service", 77),
    ]


def test_failed_runtime_restart_skips_status_probe(
    tmp_path,
    monkeypatch,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    units = tmp_path / "units"
    observed = []
    monkeypatch.setattr(systemd, "unit_root", lambda **kwargs: units)

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        observed.append((operation.action, operation.unit, check, timeout))
        if operation.action == "restart":
            raise systemd._SystemdOperationError(
                operation,
                "restart failed",
                returncode=1,
            )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)

    runtime = Gateway()
    runtime("service install --backend systemd sous chef")
    observed.clear()

    with pytest.raises(systemd._SystemdOperationError):
        runtime("service restart --timeout 66 sous chef")

    assert observed == [
        ("restart", "gway-sous-chef.service", True, 66.0),
    ]


def test_systemd_uninstall_routes_through_central_runner_with_timeout(
    tmp_path,
    record_systemd_operations,
):
    state_root = tmp_path / "state"
    unit_root = tmp_path / "units"
    services = _named_sous_services("worker")

    systemd.install_units(
        "gway",
        services,
        state_root=state_root,
        root=unit_root,
    )
    record_systemd_operations.clear()

    systemd.uninstall_units(
        "gway",
        state_root=state_root,
        root=unit_root,
        timeout=73,
    )

    assert record_systemd_operations == [
        ("disable", "gway-worker.service", False, 73),
        ("daemon-reload", None, False, 73),
    ]
