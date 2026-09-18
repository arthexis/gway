from __future__ import annotations

import os
from pathlib import Path

import pytest

import gway.logging as logging_module
import gway.runtime as runtime_module
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.errors import DispatchError
from gway.logs.command import run_log
from gway.logs.configuration import configure_consumers, consumer_environment_file
from gway.logs.publishers import clear_bindings
from gway.logging import configure, current_context, write_event
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime
from gway.service import ServiceManager


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def _isolate_consumer_logging_environment(monkeypatch):
    # Consumer activation deliberately preserves a non-secret state-file pointer
    # for reload/exec. Keep all process/context logging state test-local.
    for name in (
        "GWAY_LOG_DESTINATION",
        "GWAY_LOG_TOKEN",
        "GWAY_LOG_CONSUMER_STATE",
        "GWAY_SERVICE_ATTACHMENT_STATE",
        "GWAY_LOG_CONTEXT",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_bindings()
    yield
    for name in (
        "GWAY_LOG_DESTINATION",
        "GWAY_LOG_TOKEN",
        "GWAY_LOG_CONSUMER_STATE",
        "GWAY_SERVICE_ATTACHMENT_STATE",
        "GWAY_LOG_CONTEXT",
    ):
        os.environ.pop(name, None)
    clear_bindings()
    logging_module._run_id.set(None)
    logging_module._tags.set(())
    logging_module._destinations.set(())
    logging_module._failed_remote_destinations.set(frozenset())


class FakeWeb:
    def __init__(self) -> None:
        self.issued = 0
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
        self.issued += 1
        binding = {
            "provider": "web",
            "destination": destination,
            "configuration": {
                "transport": "http",
                "url_template": f"{destination}/api/logs/{{run_id}}/events",
                "headers": {
                    "Authorization": "Bearer {GWAY_LOG_TOKEN}",
                    "Content-Type": "application/x-ndjson",
                },
            },
            "environment": {
                "GWAY_LOG_DESTINATION": destination,
                "GWAY_LOG_TOKEN": self.token,
            },
            "metadata": {"token_id": self.token_id},
        }
        self.bindings[destination] = binding
        self.rotate = False
        return binding


def _wire_project(tmp_path: Path) -> Project:
    return Project(
        name="wire",
        path=tmp_path / "wire",
        adapter_type="python",
        adapter_config={"module": "wire"},
        aliases=("gway-wire",),
    )


def test_log_plural_consumers_accepts_csv_and_singular_accepts_one(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-consumers")

    state = run_log(
        [
            "--to",
            "https://logs.example.test",
            "--consumer",
            "wire",
            "--consumers",
            "arthexis,epaper",
        ],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
    )

    assert state["consumers"] == ["wire", "arthexis", "epaper"]
    assert state["consumer_destination"] == "https://logs.example.test"
    assert "consumer_token_id" not in state
    assert web.issued == 1
    for consumer in ("wire", "arthexis", "epaper"):
        environment = paths.data_dir / "log-consumers" / f"{consumer}.env"
        assert environment.is_file()
        assert oct(environment.stat().st_mode & 0o777) == "0o600"
        text = environment.read_text(encoding="utf-8")
        assert "GWAY_LOG_DESTINATION=\"https://logs.example.test\"" in text
        assert f'GWAY_LOG_TOKEN="{web.token}"' in text
        assert f'GWAY_LOG_CONSUMER_STATE="{paths.data_dir / "log-consumers.json"}"' in text


def test_singular_consumer_rejects_csv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_RUN_ID", "test-log-singular-consumer")
    with pytest.raises(DispatchError, match="--consumer accepts one consumer"):
        run_log(
            ["--to", "https://logs.example.test", "--consumer", "wire,arthexis"],
            dispatch=FakeWeb().dispatch,
            paths=_paths(tmp_path),
        )


def test_consumer_binding_reuses_provider_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()

    first = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    second = configure_consumers(
        ["arthexis"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert first["publisher"] == second["publisher"] == {
        "provider": "web",
        "destination": "https://logs.example.test",
    }
    assert second["consumers"] == ["wire", "arthexis"]
    assert web.issued == 1


def test_consumer_binding_accepts_provider_rotated_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    web.rotate = True
    web.token_id = "replacement"
    web.token = "gweb_v1_replacement_secret"

    result = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert result["publisher"] == {
        "provider": "web",
        "destination": "https://logs.example.test",
    }
    assert web.issued == 2


def test_log_command_result_does_not_expose_provider_secret(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-secret-result")

    state = run_log(
        [
            "--to",
            "https://logs.example.test",
            "--consumer",
            "wire",
        ],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
    )

    assert web.token not in repr(state)
    assert state["consumer_publisher"] == {
        "provider": "web",
        "destination": "https://logs.example.test",
    }


def test_consumer_credential_is_not_exported_to_shared_process_environment(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()

    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )

    assert "GWAY_LOG_TOKEN" not in os.environ
    assert "GWAY_LOG_DESTINATION" not in os.environ
    assert os.environ["GWAY_LOG_CONSUMER_STATE"] == str(paths.data_dir / "log-consumers.json")


def test_alias_reconfiguration_collapses_to_canonical_consumer(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    project = _wire_project(tmp_path)

    # Simulate wiring an alias before its project has been registered.
    configure_consumers(
        ["gway-wire"],
        ["https://old.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
    )

    def resolve(name: str) -> Project | None:
        return project if name.casefold() in {"wire", "gway-wire"} else None

    configure_consumers(
        ["wire"],
        ["https://new.example.test"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=resolve,
    )

    environment = consumer_environment_file(project, paths=paths)
    assert environment == paths.data_dir / "log-consumers" / "wire.env"
    assert 'GWAY_LOG_DESTINATION="https://new.example.test"' in environment.read_text(
        encoding="utf-8"
    )
    assert not (paths.data_dir / "log-consumers" / "gway-wire.env").exists()


def test_consumer_environment_matches_project_alias(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    configure_consumers(
        ["gway-wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    project = _wire_project(tmp_path)

    environment = consumer_environment_file(project, paths=paths)

    assert environment == paths.data_dir / "log-consumers" / "gway-wire.env"


def test_runtime_routes_log_consumers_through_active_registry(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    registry = Registry(paths=paths)
    dispatcher = Dispatcher(registry=registry)
    runtime = GwayRuntime(dispatcher)
    captured: dict[str, object] = {}

    def fake_run_log(argv, **kwargs):
        captured["argv"] = list(argv)
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(runtime_module, "run_log", fake_run_log)

    result = runtime._run_core(["log", "--consumers", "wire"])

    assert result == {"ok": True}
    assert captured["paths"] is paths
    assert getattr(captured["dispatch"], "__self__", None) is dispatcher
    assert getattr(captured["resolve_consumer"], "__self__", None) is registry


def test_service_render_injects_private_consumer_environment(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    monkeypatch.setenv("GWAY_DATA_HOME", str(paths.data_dir))
    web = FakeWeb()
    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=web.dispatch,
        paths=paths,
    )
    project_path = tmp_path / "wire"
    project_path.mkdir()
    (project_path / "gway.toml").write_text(
        """[project]
name = "wire"

[adapter]
type = "python"
module = "wire"

[service]
command = ["/bin/true"]
""",
        encoding="utf-8",
    )
    project = Project.from_path(project_path)

    rendered = ServiceManager(project, unit_directory=tmp_path / "systemd").render(user="root")

    expected = paths.data_dir / "log-consumers" / "wire.env"
    assert f'EnvironmentFile="{expected}"' in rendered
    assert web.token not in rendered


def test_managed_service_destination_seeds_new_log_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-service-log-default")
    monkeypatch.setenv("GWAY_LOG_DESTINATION", "https://logs.example.test")
    monkeypatch.delenv("GWAY_LOG_CONTEXT", raising=False)

    state = current_context()

    assert state["to"] == ["https://logs.example.test"]


def test_consumer_names_are_safe_for_environment_paths(tmp_path: Path) -> None:
    with pytest.raises(DispatchError, match="invalid log consumer"):
        configure_consumers(
            ["../wire"],
            ["https://logs.example.test"],
            dispatch=FakeWeb().dispatch,
            paths=_paths(tmp_path),
        )


def test_consumer_destination_requires_http_authority(tmp_path: Path) -> None:
    with pytest.raises(DispatchError, match="requires an authority"):
        configure_consumers(
            ["wire"],
            ["https:///logs.example.test"],
            dispatch=FakeWeb().dispatch,
            paths=_paths(tmp_path),
        )


def test_explicit_destination_moves_consumer_from_existing_sink(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    web = FakeWeb()
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-move-consumer")
    monkeypatch.setattr(logging_module, "publish_remote", lambda *_args: True)

    run_log(
        ["--to", "https://old.example.test", "--consumer", "wire"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
    )
    result = run_log(
        ["--to", "https://new.example.test", "--consumer", "wire"],
        dispatch=web.dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
    )

    assert result["consumer_destination"] == "https://new.example.test"
    environment = paths.data_dir / "log-consumers" / "wire.env"
    assert 'GWAY_LOG_DESTINATION="https://new.example.test"' in environment.read_text(
        encoding="utf-8"
    )


def test_consumer_activation_retries_previously_failed_sink(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    destination = "https://logs.example.test"
    calls: list[bytes] = []
    accepting = False

    def publish(_destination: str, _run_id: str, data: bytes) -> bool:
        calls.append(data)
        return accepting

    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "test-retry-consumer")
    monkeypatch.setattr(logging_module, "publish_remote", publish)

    configure(to=(destination,))
    assert destination in logging_module._failed_remote_destinations.get()
    initial_calls = len(calls)

    accepting = True
    configure_consumers(
        ["wire"],
        [destination],
        dispatch=FakeWeb().dispatch,
        paths=paths,
    )

    assert destination not in logging_module._failed_remote_destinations.get()
    assert len(calls) > initial_calls
    after_activation = len(calls)
    write_event("test.after-token", "publisher recovered")
    assert len(calls) == after_activation + 1
