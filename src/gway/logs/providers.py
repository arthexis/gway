from __future__ import annotations

from collections.abc import Callable

from ..dispatcher.errors import DispatchError
from .interface import LogPublisherProvider

ProviderResolver = Callable[[str], LogPublisherProvider | None]


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


__all__ = ["ProviderResolver", "resolve_provider"]
