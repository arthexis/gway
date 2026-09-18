from __future__ import annotations

import json
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher.errors import DispatchError
from gway.logs import PublisherBinding, ServiceRef
from gway.logs.command import run_log
from gway.logs.configuration import configure_consumers
from gway.logs.providers import CommandLogPublisherProvider
from gway.logs.publishers import binding_for, clear_bindings, set_binding


class FixtureProvider:
    name = "fixture"

    def __init__(self) -> None:
        self.currents: list[PublisherBinding | None] = []

    def provision(
        self,
        *,
        destination: str,
        consumer: str,
        service=None,
        current: PublisherBinding | None = None,
    ) -> PublisherBinding:
        self.currents.append(current)
        if current is not None:
            return current
        return PublisherBinding(
            provider=self.name,
            destination=destination,
            configuration={"consumer": consumer},
            environment={"FIXTURE_LOG_DESTINATION": destination},
            metadata={"binding_id": "fixture-1"},
        )


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")


def test_consumer_configuration_uses_resolved_provider_without_web_dispatch(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    provider = FixtureProvider()

    def reject_dispatch(_project: str, _tokens) -> object:
        raise AssertionError("custom provider must not invoke Web")

    result = configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=reject_dispatch,
        paths=paths,
        provider="fixture",
        provider_resolver=lambda name: provider if name == "fixture" else None,
    )

    assert result["provider"] == "fixture"
    publisher = result["publisher"]
    assert isinstance(publisher, dict)
    assert publisher == {
        "provider": "fixture",
        "destination": "https://logs.example.test",
    }

    environment = paths.data_dir / "log-consumers" / "wire.env"
    contents = environment.read_text(encoding="utf-8")
    assert 'FIXTURE_LOG_DESTINATION="https://logs.example.test"' in contents
    assert 'GWAY_LOG_DESTINATION="https://logs.example.test"' in contents
    assert f'GWAY_LOG_CONSUMER_STATE="{paths.data_dir / "log-consumers.json"}"' in contents

    state = json.loads((paths.data_dir / "log-consumers.json").read_text(encoding="utf-8"))
    record = state["bindings"]["https://logs.example.test"]
    assert record["provider"] == "fixture"
    assert record["publisher"]["provider"] == "fixture"


def test_provider_receives_current_persisted_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    provider = FixtureProvider()

    def resolver(name: str):
        return provider if name == "fixture" else None

    configure_consumers(
        ["wire"],
        ["https://logs.example.test"],
        dispatch=lambda _project, _tokens: None,
        paths=paths,
        provider="fixture",
        provider_resolver=resolver,
    )
    configure_consumers(
        ["arthexis"],
        ["https://logs.example.test"],
        dispatch=lambda _project, _tokens: None,
        paths=paths,
        provider="fixture",
        provider_resolver=resolver,
    )

    assert provider.currents[0] is None
    current = provider.currents[1]
    assert current is not None
    assert current.provider == "fixture"
    assert current.metadata == {"binding_id": "fixture-1"}


def test_log_command_selects_explicit_provider(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    provider = FixtureProvider()
    monkeypatch.setenv("GWAY_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GWAY_RUN_ID", "provider-binding")

    def reject_dispatch(_project: str, _tokens) -> object:
        raise AssertionError("custom provider must not invoke Web")

    def resolver(name: str):
        return provider if name == "fixture" else None

    state = run_log(
        [
            "--to",
            "https://logs.example.test",
            "--consumer",
            "wire",
            "--publisher",
            "fixture",
        ],
        dispatch=reject_dispatch,
        paths=paths,
        resolve_consumer=lambda _name: None,
        resolve_provider=resolver,
    )

    assert state["consumer_provider"] == "fixture"
    publisher = state["consumer_publisher"]
    assert isinstance(publisher, dict)
    assert publisher["provider"] == "fixture"
    assert "consumer_token_id" not in state


def test_command_provider_keeps_current_binding_out_of_dispatch_arguments() -> None:
    calls: list[tuple[str, list[str]]] = []

    def dispatch(project: str, tokens) -> object:
        calls.append((project, list(tokens)))
        return {
            "provider": "fixture",
            "destination": "https://logs.example.test",
            "configuration": {"mode": "remote"},
            "environment": {"FIXTURE_TOKEN": "secret"},
            "metadata": {"binding_id": "replacement"},
        }

    current = PublisherBinding(
        provider="fixture",
        destination="https://logs.example.test",
        configuration={"mode": "remote"},
        environment={"FIXTURE_TOKEN": "old-secret"},
        metadata={"binding_id": "current"},
    )
    provider = CommandLogPublisherProvider("fixture", dispatch)

    binding = provider.provision(
        destination="https://logs.example.test",
        consumer="wire",
        service=ServiceRef(project="wire", service="worker"),
        current=current,
    )

    assert binding.metadata == {"binding_id": "replacement"}
    project, argv = calls[0]
    assert project == "fixture"
    assert argv[:5] == [
        "log-publisher",
        "--destination",
        "https://logs.example.test",
        "--consumer",
        "wire",
    ]
    assert argv[argv.index("--service-project") + 1] == "wire"
    assert argv[argv.index("--service") + 1] == "worker"
    assert "--current" not in argv
    assert "old-secret" not in repr(argv)


def test_command_provider_rejects_invalid_binding_record() -> None:
    provider = CommandLogPublisherProvider(
        "fixture",
        lambda _project, _tokens: {"provider": "fixture"},
    )

    with pytest.raises(DispatchError, match="invalid binding record"):
        provider.provision(
            destination="https://logs.example.test",
            consumer="wire",
        )


def test_publisher_binding_context_starts_empty() -> None:
    clear_bindings()
    binding = PublisherBinding(
        provider="fixture",
        destination="https://logs.example.test",
    )
    set_binding(binding)
    assert binding_for(binding.destination) == binding
    clear_bindings()
    assert binding_for(binding.destination) is None
