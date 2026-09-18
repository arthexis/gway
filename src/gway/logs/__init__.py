from __future__ import annotations

from .binding import LogBinding, PublisherBinding, ServiceRef
from .consumers import ConsumerResolver, normalize_consumers
from .interface import LogPublisherProvider
from .providers import CommandLogPublisherProvider, ProviderResolver, resolve_provider

_LAZY_EXPORTS = {
    "activate_publishers",
    "configure_consumers",
    "consumer_environment_file",
    "publisher_binding",
    "run_log",
}


def __getattr__(name: str):
    if name == "run_log":
        from .command import run_log

        return run_log
    if name in {
        "activate_publishers",
        "configure_consumers",
        "consumer_environment_file",
        "publisher_binding",
    }:
        from . import configuration

        return getattr(configuration, name)
    raise AttributeError(name)


__all__ = [
    "CommandLogPublisherProvider",
    "ConsumerResolver",
    "LogBinding",
    "LogPublisherProvider",
    "ProviderResolver",
    "PublisherBinding",
    "ServiceRef",
    "activate_publishers",
    "configure_consumers",
    "consumer_environment_file",
    "normalize_consumers",
    "publisher_binding",
    "resolve_provider",
    "run_log",
]
