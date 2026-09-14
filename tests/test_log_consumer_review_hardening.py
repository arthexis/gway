from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import gway.log_consumers as consumers_module
from gway.adapters import AdapterRegistry
from gway.command import Command
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.dispatch import redact_command_results
from gway.log_consumers import configure_consumers
from gway.project import Project
from gway.registry import Registry
from gway.service import ServiceManager


class FakeWeb:
    def __init__(self) -> None:
        self.token_id = "local-ingest"
        self.token = "gweb_v1_local-ingest_secret"
        self.revoked = False

    def dispatch(self, project: str, tokens) -> object:
        assert project == "web"
        if "--list" in tokens:
            return [
                {
                    "token_id": self.token_id,
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(days=30)
                    ).isoformat(),
                    "revoked_at": (
                        datetime.now(timezone.utc).isoformat() if self.revoked else None
                    ),
                }
            ]
        return {"token_id": self.token_id, "token": self.token}


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
    dispatch_module = importlib.import_module("gway.dispatcher.dispatch")
    monkeypatch.setattr(
        dispatch_module,
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

    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=FakeWeb().dispatch,
        paths=paths,
        resolve_consumer=lambda name: project if name.casefold() in {"wire", "gway-wire"} else None,
    )

    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(user="root")
    expected = paths.data_dir / "log-consumers" / "wire.env"
    assert f'EnvironmentFile="{expected}"' in rendered


def test_rotated_token_refreshes_registered_consumers(tmp_path: Path, monkeypatch) -> None:
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
    assert refreshed == []

    web.revoked = True
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
