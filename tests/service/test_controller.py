import time

import pytest

from gway import Gateway
from gway.install.service import ServiceInstallState
from gway.sampler import root as sampler_root
from gway.service.model import Service


class FakeBackend:
    def __init__(self):
        self.calls = []

    def _result(self, action, service):
        self.calls.append((action, service.identity, service.launchable.name))
        return {
            "project": service.project,
            "service": service.name,
            "action": action,
        }

    def start(self, service):
        return self._result("start", service)

    def stop(self, service):
        return self._result("stop", service)

    def restart(self, service):
        return self._result("restart", service)

    def status(self, service):
        return self._result("status", service)


@pytest.fixture
def service_gateway():
    gateway = Gateway()
    gateway.wrap("worker", lambda: "worked")
    backend = FakeBackend()
    gateway._service_controller.backend = backend
    return gateway, backend


def test_service_list_contains_named_presets():
    gateway = Gateway()

    listed = gateway("service list")

    assert listed == [
        {
            "project": "gway",
            "service": "sous-chef",
            "description": "Gway single-worker recipe scheduler",
            "launchable": "operation",
            "target": "sous.chef",
        }
    ]


def test_service_list_can_filter_presets_by_project():
    gateway = Gateway()
    gateway.wrap("demo worker", lambda: None)
    launchable = gateway.launchables["demo.worker"]
    preset = Service.from_launchable(
        "demo",
        "worker",
        launchable.root or ".",
        launchable,
        description="Demo worker",
    )
    gateway._service_presets[preset.identity] = preset

    assert gateway("service list --project demo") == [
        {
            "project": "demo",
            "service": "worker",
            "description": "Demo worker",
            "launchable": "operation",
            "target": "demo.worker",
        }
    ]


def test_service_inspect_materializes_policy_for_any_operation(service_gateway):
    gateway, _ = service_gateway

    inspected = gateway("service inspect worker")

    assert inspected["project"] == "gway"
    assert inspected["service"] == "worker"
    assert inspected["launchable"]["name"] == "worker"
    assert inspected["restart"] == "on-failure"
    assert inspected["attempts"] == 3


@pytest.mark.parametrize("action", ["start", "stop", "restart", "status"])
def test_service_lifecycle_commands_delegate_to_backend(service_gateway, action):
    gateway, backend = service_gateway

    result = gateway(f"service {action} worker")

    assert result == {
        "project": "gway",
        "service": "worker",
        "action": action,
    }
    assert backend.calls == [(action, ("gway", "worker"), "worker")]


def test_unknown_service_target_has_clear_resolution_error(service_gateway):
    gateway, _ = service_gateway

    with pytest.raises(LookupError):
        gateway("service start missing-operation")


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "-inf"])
def test_service_timeout_rejects_non_positive_or_non_finite_values(
    service_gateway,
    timeout,
):
    gateway, backend = service_gateway

    with pytest.raises(
        ValueError, match="service timeout must be a finite positive number"
    ):
        gateway(f"service restart --timeout {timeout} worker")

    assert backend.calls == []


@pytest.mark.parametrize(
    "timeout",
    [float("nan"), float("inf"), float("-inf")],
)
def test_timeout_normalizer_rejects_non_finite_numeric_values(
    service_gateway,
    timeout,
):
    gateway, _ = service_gateway

    with pytest.raises(
        ValueError, match="service timeout must be a finite positive number"
    ):
        gateway._service_controller._timeout(timeout)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.5", 0.5), ("40", 40.0), (125.25, 125.25)],
)
def test_timeout_normalizer_accepts_finite_positive_values(
    service_gateway,
    value,
    expected,
):
    gateway, _ = service_gateway

    assert gateway._service_controller._timeout(value) == expected



def test_mcp_recipe_resolves_as_generic_gway_service():
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"

    definition = gateway._service_controller._definition(
        (str(recipe),),
        name="mcp-server",
    )

    assert definition.identity == ("gway", "mcp-server")
    assert definition.launchable.kind == "recipe"
    assert definition.launchable.name == "server"
    assert definition.launchable.target == recipe.resolve()
    assert definition.launchable.command[:3] == ("{python}", "-m", "gway")
    assert definition.launchable.command[3] == str(recipe.resolve())


def test_mcp_recipe_installs_through_generic_process_backend(tmp_path, monkeypatch):
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"
    data_root = tmp_path / "gway-data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))

    records = gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="mcp-server",
    )

    assert len(records) == 1
    record = records[0]
    assert record.project == "gway"
    assert record.service == "mcp-server"
    assert record.backend == "process"
    assert record.backend_id == "mcp-server"
    assert record.command[:3] == ("{python}", "-m", "gway")
    assert record.command[3] == str(recipe.resolve())

    persisted = ServiceInstallState(data_root / "services-installed").get("gway")
    assert persisted == records



def test_installed_mcp_process_service_lifecycle(tmp_path, monkeypatch):
    gateway = Gateway()
    recipe = sampler_root() / "mcp" / "server.rx"
    data_root = tmp_path / "gway-data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data_root))

    gateway._service_controller.install(
        str(recipe),
        backend="process",
        name="mcp-server",
        restart="no",
    )

    started = gateway._service_controller.start(
        str(recipe),
        name="mcp-server",
    )
    first_pid = started["pid"]

    try:
        assert started["project"] == "gway"
        assert started["service"] == "mcp-server"
        assert started["running"] is True
        assert first_pid is not None

        deadline = time.monotonic() + 5
        status = gateway._service_controller.status(
            str(recipe),
            name="mcp-server",
        )
        while time.monotonic() < deadline and not status["running"]:
            time.sleep(0.05)
            status = gateway._service_controller.status(
                str(recipe),
                name="mcp-server",
            )

        assert status["running"] is True
        assert status["pid"] == first_pid

        restarted = gateway._service_controller.restart(
            str(recipe),
            name="mcp-server",
        )
        assert restarted["running"] is True
        assert restarted["pid"] is not None
        assert restarted["pid"] != first_pid

        restarted_status = gateway._service_controller.status(
            str(recipe),
            name="mcp-server",
        )
        assert restarted_status["running"] is True
        assert restarted_status["pid"] == restarted["pid"]
    finally:
        stopped = gateway._service_controller.stop(
            str(recipe),
            name="mcp-server",
        )

    assert stopped == {
        "project": "gway",
        "service": "mcp-server",
        "running": False,
        "pid": None,
        "started_at": None,
        "stale": False,
    }
