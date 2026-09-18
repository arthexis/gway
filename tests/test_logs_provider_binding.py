from __future__ import annotations

import json
from pathlib import Path

from gway.config import GwayPaths
from gway.log_command import run_log
from gway.log_consumers import configure_consumers
from gway.logs import PublisherBinding


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
    assert publisher["metadata"] == {"binding_id": "fixture-1"}

    environment = paths.data_dir / "log-consumers" / "wire.env"
    assert environment.read_text(encoding="utf-8") == (
        'FIXTURE_LOG_DESTINATION="https://logs.example.test"\n'
    )

    state = json.loads((paths.data_dir / "log-consumers.json").read_text(encoding="utf-8"))
    record = state["bindings"]["https://logs.example.test"]
    assert record["provider"] == "fixture"
    assert record["publisher"]["provider"] == "fixture"


def test_provider_receives_current_persisted_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    provider = FixtureProvider()
    resolver = lambda name: provider if name == "fixture" else None

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
        resolve_provider=lambda name: provider if name == "fixture" else None,
    )

    assert state["consumer_provider"] == "fixture"
    publisher = state["consumer_publisher"]
    assert isinstance(publisher, dict)
    assert publisher["provider"] == "fixture"
    assert "consumer_token_id" not in state
