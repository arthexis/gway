import pytest

import gway.install.service.systemd as systemd
from gway import Gateway
from gway.install.service import ServiceInstallState


def _service(name):
    runtime = Gateway()
    return runtime._service_controller._definition(("sous", "chef"), name=name)


def test_no_enable_requires_disable_to_succeed(tmp_path, monkeypatch):
    observed = []

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        observed.append((operation.action, operation.unit, check))
        if operation.action == "disable" and check:
            raise systemd._SystemdOperationError(
                operation,
                "disable failed",
                returncode=1,
                stderr="cannot disable unit",
            )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)

    state_root = tmp_path / "state"
    with pytest.raises(systemd._SystemdOperationError, match="disable failed"):
        systemd.install_units(
            "gway",
            [_service("simulator")],
            state_root=state_root,
            root=tmp_path / "units",
            enable=False,
        )

    assert ("disable", "gway-simulator.service", True) in observed
    assert ServiceInstallState(state_root).get("gway") == []


def test_disabled_policy_is_persisted(tmp_path, monkeypatch):
    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)
    state_root = tmp_path / "state"

    records = systemd.install_units(
        "gway",
        [_service("simulator")],
        state_root=state_root,
        root=tmp_path / "units",
        enable=False,
    )

    assert records[0].enabled is False
    restored = ServiceInstallState(state_root).get("gway")
    assert restored[0].enabled is False


def test_legacy_install_state_defaults_to_enabled(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "gway.json").write_text(
        '[{"project":"gway","service":"web","backend_id":"gway-web.service"}]'
    )

    record = ServiceInstallState(state_root).get("gway")[0]

    assert record.enabled is True


def test_failed_later_install_restores_prior_disabled_policy(tmp_path, monkeypatch):
    observed = []
    fail_enable = False

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        nonlocal fail_enable
        observed.append((operation.action, operation.unit, check))
        if fail_enable and operation.action == "enable" and check:
            raise systemd._SystemdOperationError(
                operation,
                "enable failed",
                returncode=1,
            )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)
    state_root = tmp_path / "state"
    units = tmp_path / "units"

    systemd.install_units(
        "gway",
        [_service("simulator")],
        state_root=state_root,
        root=units,
        enable=False,
    )
    observed.clear()
    fail_enable = True

    with pytest.raises(systemd._SystemdOperationError, match="enable failed"):
        systemd.install_units(
            "gway",
            [_service("worker")],
            state_root=state_root,
            root=units,
            enable=True,
        )

    # Rollback restores the prior simulator policy as disabled instead of
    # unconditionally enabling every previously-installed systemd unit.
    assert ("disable", "gway-simulator.service", False) in observed
    restored = ServiceInstallState(state_root).get("gway")
    assert [(record.service, record.enabled) for record in restored] == [
        ("simulator", False)
    ]
