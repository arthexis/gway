from __future__ import annotations

from pathlib import Path

from gway.logs import LogBinding, LogPublisherProvider, PublisherBinding, ServiceRef
from gway.project import Project


class FixtureProvider:
    name = "fixture"

    def provision(
        self,
        *,
        destination: str,
        consumer: Project,
        service: ServiceRef | None = None,
    ) -> PublisherBinding:
        return PublisherBinding(
            provider=self.name,
            destination=destination,
            configuration={"consumer": consumer.name},
            metadata={"service": service.service if service is not None else None},
        )


def _project() -> Project:
    return Project(
        name="consumer",
        path=Path("/tmp/consumer"),
        adapter_type="python",
        adapter_config={},
    )


def test_logging_provider_contract_is_runtime_checkable() -> None:
    provider = FixtureProvider()
    assert isinstance(provider, LogPublisherProvider)


def test_provider_returns_opaque_publisher_binding() -> None:
    provider = FixtureProvider()
    service = ServiceRef(project="consumer", service="worker")
    binding = provider.provision(
        destination="https://logs.example.test",
        consumer=_project(),
        service=service,
    )

    assert binding == PublisherBinding(
        provider="fixture",
        destination="https://logs.example.test",
        configuration={"consumer": "consumer"},
        metadata={"service": "worker"},
    )


def test_log_binding_composes_consumer_service_and_publisher() -> None:
    publisher = PublisherBinding(
        provider="fixture",
        destination="https://logs.example.test",
        configuration={"opaque": "value"},
    )
    service = ServiceRef(project="consumer", service="worker")

    binding = LogBinding(
        consumer="consumer",
        service=service,
        publisher=publisher,
    )

    assert binding.consumer == "consumer"
    assert binding.service == service
    assert binding.publisher is publisher
