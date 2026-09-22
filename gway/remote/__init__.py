"""Shared remote-access infrastructure for G-Way."""

from .metadata import RemoteOAuthMetadata
from .server import RemoteDiscoveryApplication, build_server, serve

__all__ = [
    "RemoteDiscoveryApplication",
    "RemoteOAuthMetadata",
    "build_server",
    "serve",
]
