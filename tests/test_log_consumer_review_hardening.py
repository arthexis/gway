from __future__ import annotations

import importlib
import threading
import time
from pathlib import Path

import pytest

import gway.log_consumers as consumers_module
from gway.logs.state import state_lock
from gway.adapters import AdapterRegistry
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.outcome import redact_command_results
from gway.dispatcher.errors import DispatchError
from gway.log_consumers import configure_consumers
from gway.project import Project
from gway.registry import Registry
from gway.service import ServiceManager


class FakeWeb:
    def __init__(self) -> None:
        self.token_id = "local-ingest"
        self.token = "gweb_v1_local-ingest_secret"
        self.rotate = False
        self.bindings: dict[str, dict[str, object]] = {}

    def dispatch(self, project: str, tokens) -> object:
        assert project == "web"
        assert tokens[0] == "log-publisher"
        destination = tokens[tokens.index("--destination") + 1]
        current = self.bindings.get(destination)
        if current is not None and not self.rotate:
            return current
        binding = {
            "provider": "web",
            "destination": destination,
            "configuration": {},
            "environment": {
                "GWAY_LOG_DESTINATION": destination,
                "GWAY_LOG_TOKEN": self.token,
            },
            "metadata": {"token_id": self.token_id},
        }
        self.bindings[destination] = binding
        self.rotate = False
        return binding


class SecretAdapter:
    def __init__(self, project: Project) -> None:
        self.project = project

    def commands(self) -> tuple[Command, ...]:
        return (Command(("secret",), summary="Return a sensitive result."),)

    def describe(self, path: tuple[str, ...]) -> Command:
        return self.commands()[0]

    def run(self, path: tuple[str, ...], argv: list[str]) -> object:
        assert path == ("secret",)
        return {"token": "super-secret", "token_id": "token-1"}


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(tmp_path / "config", tmp_path / "data")


@pytest.fixture(autouse=True)
def _isolate_service_attachment_state(monkeypatch):
    monkeypatch.delenv("GWAY_SERVICE_ATTACHMENT_STATE", raising=False)


def _service_project(tmp_path: Path) -> Project:
    path = tmp_path / "wire"
    path.mkdir(exist_ok=True)
    (path / "gway.toml").write_text(
        """[project]
name = "wire"
aliases = ["gway-wire"]

[adapter]
type = "python"
module = "wire"

[service]
command = ["/bin/true"]
""",
        encoding="utf-8",
    )
    return Project.from_path(path)


def test_redacted_dispatch_returns_secret_without_logging_it(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "secret-project"
    project_root.mkdir()
    (project_root / "gway.toml").write_text(
        """[project]
name = "secret-project"

[adapter]
type = "secret"
""",
        encoding="utf-8",
    )
    registry = Registry(_paths(tmp_path))
    registry.register_path(project_root)
    adapters = AdapterRegistry()
    adapters.register("secret", SecretAdapter)
    dispatcher = Dispatcher(registry, adapters)
    events: list[tuple[str, dict[str, object]]] = []
    outcome_module = importlib.import_module("gway.dispatcher.outcome")
    monkeypatch.setattr(
        outcome_module,
        "record",
        lambda kind, message, **data: events.append((kind, data)),
    )

    with redact_command_results():
        result = dispatcher.run("secret-project", ["secret"])

    assert result == {"token": "super-secret", "token_id": "token-1"}
    command_result = next(data for kind, data in events if kind == "command.result")
    assert command_result["result"] == "<redacted>"
    assert "super-secret" not in repr(events)


def test_consumer_environment_uses_active_state_pointer(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    project = _service_project(tmp_path)
    monkeypatch.delenv("GWAY_DATA_HOME", raising=False)
    monkeypatch.delenv("GWAY_LOG_CONSUMER_STATE", raising=False)

    def resolve(name: str) -> Project | None:
        return project if name.casefold() in {"wire", "gway-wire"} else None

    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=FakeWeb().dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )

    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(user="root")
    expected = paths.data_dir / "log-consumers" / "wire.env"
    assert f'EnvironmentFile="{expected}"' in rendered


def test_remote_consumer_destinations_require_transport_security() -> None:
    assert consumers_module._remote_destination(["http://127.0.0.1:8040"]) == (
        "http://127.0.0.1:8040"
    )
    assert consumers_module._remote_destination(["http://[::1]:8040"]) == "http://[::1]:8040"
    assert consumers_module._remote_destination(["https://logs.example.test"]) == (
        "https://logs.example.test"
    )
    with pytest.raises(DispatchError, match="must use HTTPS unless loopback"):
        consumers_module._remote_destination(["http://logs.example.test"])


def test_state_lock_serializes_writers(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    active = 0
    maximum_active = 0
    guard = threading.Lock()
    ready = threading.Barrier(2)

    def worker() -> None:
        nonlocal active, maximum_active
        ready.wait()
        with state_lock(paths):
            with guard:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.05)
            with guard:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert maximum_active == 1


def test_environment_change_refreshes_registered_consumers(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    project = _service_project(tmp_path)
    web = FakeWeb()
    refreshed: list[str] = []

    def resolve(name: str) -> Project | None:
        return project if name.casefold() in {"wire", "gway-wire"} else None

    monkeypatch.setattr(
        consumers_module,
        "_refresh_running_consumer_services",
        lambda consumers, resolver: refreshed.extend(consumers) or ["gway-wire.service"],
    )

    first = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )
    assert refreshed == ["wire"]
    assert first["refreshed_services"] == ["gway-wire.service"]

    refreshed.clear()
    unchanged = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )
    assert refreshed == []
    assert "refreshed_services" not in unchanged

    moved = configure_consumers(
        ["wire"],
        ["https://other-logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )
    assert refreshed == ["wire"]
    assert moved["refreshed_services"] == ["gway-wire.service"]


def test_provider_rotated_binding_refreshes_registered_consumers(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    project = _service_project(tmp_path)
    web = FakeWeb()
    refreshed: list[str] = []

    def resolve(name: str) -> Project | None:
        return project if name.casefold() in {"wire", "gway-wire"} else None

    monkeypatch.setattr(
        consumers_module,
        "_refresh_running_consumer_services",
        lambda consumers, resolver: refreshed.extend(consumers) or ["gway-wire.service"],
    )

    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )
    refreshed.clear()

    web.rotate = True
    web.token_id = "replacement"
    web.token = "gweb_v1_replacement_secret"
    result = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )

    assert refreshed == ["wire"]
    assert result["refreshed_services"] == ["gway-wire.service"]
