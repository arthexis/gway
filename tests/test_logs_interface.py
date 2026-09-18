from __future__ import annotations

from gway.logs import LogBinding, LogPublisherProvider, PublisherBinding, ServiceRef


class FixtureProvider:
    name = "fixture"

    def provision(
        self,
        *,
        destination: str,
        consumer: str,
        service: ServiceRef | None = None,
        current: PublisherBinding | None = None,
    ) -> PublisherBinding:
        return PublisherBinding(
            provider=self.name,
            destination=destination,
            configuration={"consumer": consumer},
            metadata={"service": service.service if service is not None else None},
        )


def test_logging_provider_contract_is_runtime_checkable() -> None:
    provider = FixtureProvider()
    assert isinstance(provider, LogPublisherProvider)


def test_provider_returns_opaque_publisher_binding() -> None:
    provider = FixtureProvider()
    service = ServiceRef(project="consumer", service="worker")
    binding = provider.provision(
        destination="https://logs.example.test",
        consumer="consumer",
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
