import pytest

from gway import Gateway
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


@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_service_timeout_must_be_positive(service_gateway, timeout):
    gateway, backend = service_gateway

    with pytest.raises(ValueError, match="service timeout must be greater than zero"):
        gateway(f"service restart --timeout {timeout} worker")

    assert backend.calls == []
