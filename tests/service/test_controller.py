from pathlib import Path

import pytest

from gway import Gateway
from gway.service.model import Service


class FakeBackend:
    def __init__(self):
        self.calls = []

    def _result(self, action, service):
        self.calls.append((action, service.identity))
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
def service_gateway(tmp_path):
    gateway = Gateway()
    alpha = Service(
        project="arthexis",
        name="worker",
        root=tmp_path,
        command=("{python}", "-m", "worker"),
        description="Worker",
        profiles=("Control",),
    )
    beta = Service(
        project="arthexis",
        name="beat",
        root=tmp_path,
        command=("{python}", "-m", "beat"),
        description="Beat",
    )
    gateway._services = {
        alpha.identity: alpha,
        beta.identity: beta,
    }
    backend = FakeBackend()
    gateway._service_controller.backend = backend
    return gateway, backend


def test_service_list_uses_project_owned_identity(service_gateway):
    gateway, _ = service_gateway

    assert gateway("service list") == [
        {
            "project": "arthexis",
            "service": "beat",
            "description": "Beat",
            "profiles": [],
        },
        {
            "project": "arthexis",
            "service": "worker",
            "description": "Worker",
            "profiles": ["Control"],
        },
    ]


def test_service_list_can_filter_one_project(service_gateway, tmp_path):
    gateway, _ = service_gateway
    other = Service(
        project="wire",
        name="worker",
        root=tmp_path,
        command=("{python}", "-m", "worker"),
    )
    gateway._services[other.identity] = other

    listed = gateway("service list --project wire")

    assert listed == [
        {
            "project": "wire",
            "service": "worker",
            "description": None,
            "profiles": [],
        }
    ]


def test_service_inspect_returns_normalized_definition(service_gateway):
    gateway, _ = service_gateway

    inspected = gateway("service inspect arthexis worker")

    assert inspected["project"] == "arthexis"
    assert inspected["service"] == "worker"
    assert inspected["command"] == ["{python}", "-m", "worker"]
    assert inspected["profiles"] == ["Control"]


@pytest.mark.parametrize("action", ["start", "stop", "restart", "status"])
def test_service_lifecycle_commands_delegate_to_backend(service_gateway, action):
    gateway, backend = service_gateway

    result = gateway(f"service {action} arthexis worker")

    assert result == {
        "project": "arthexis",
        "service": "worker",
        "action": action,
    }
    assert backend.calls == [(action, ("arthexis", "worker"))]


def test_unknown_service_has_clear_error(service_gateway):
    gateway, _ = service_gateway

    with pytest.raises(LookupError, match="Unknown service"):
        gateway("service start arthexis missing")
