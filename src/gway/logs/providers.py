from __future__ import annotations

from collections.abc import Callable, Sequence

from ..dispatcher.errors import DispatchError
from ..dispatcher.outcome import redact_command_results
from .binding import PublisherBinding, ServiceRef
from .interface import LogPublisherProvider

ProviderResolver = Callable[[str], LogPublisherProvider | None]
ProviderDispatch = Callable[[str, Sequence[str]], object]


class CommandLogPublisherProvider:
    """Adapt one registered GWAY project to the logging-provider protocol."""

    def __init__(self, name: str, dispatch: ProviderDispatch) -> None:
        self.name = name
        self.dispatch = dispatch

    def provision(
        self,
        *,
        destination: str,
        consumer: str,
        service: ServiceRef | None = None,
        current: PublisherBinding | None = None,
    ) -> PublisherBinding:
        argv = [
            "log-publisher",
            "--destination",
            destination,
            "--consumer",
            consumer,
        ]
        if service is not None:
            argv.extend(("--service-project", service.project))
            argv.extend(("--service", service.service))
        # Command-backed providers own credential lifecycle and persistence. Do
        # not serialize the current binding into argv: bindings may contain
        # provider secrets and dispatcher argument instrumentation is observable.
        # Provisioning results may contain provider credentials. Keep the result
        # available to the caller while excluding it from dispatcher event logs.
        with redact_command_results():
            result = self.dispatch(self.name, argv)
        if not isinstance(result, dict):
            raise DispatchError(
                f"log publisher provider {self.name!r} did not return a binding record"
            )
        binding = PublisherBinding.from_record(result)
        if binding is None:
            raise DispatchError(
                f"log publisher provider {self.name!r} returned an invalid binding record"
            )
        return binding


def resolve_provider(
    name: str,
    resolver: ProviderResolver,
) -> LogPublisherProvider:
    """Resolve one named logging provider through a caller-owned registry."""
    provider = resolver(name)
    if provider is None:
        raise DispatchError(f"unknown log publisher provider: {name}")
    if provider.name.casefold() != name.casefold():
        raise DispatchError(
            f"log publisher provider {name!r} resolved as {provider.name!r}"
        )
    return provider


__all__ = [
    "CommandLogPublisherProvider",
    "ProviderDispatch",
    "ProviderResolver",
    "resolve_provider",
]
