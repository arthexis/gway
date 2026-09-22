"""Shared remote-access infrastructure for G-Way."""

from .account import RemoteAccountApplication
from .metadata import RemoteOAuthMetadata
from .server import (
    RemoteApplication,
    RemoteDiscoveryApplication,
    build_server,
    serve,
)
from .session import RemoteSession, RemoteSessionStore

__all__ = [
    "RemoteAccountApplication",
    "RemoteApplication",
    "RemoteDiscoveryApplication",
    "RemoteOAuthMetadata",
    "RemoteSession",
    "RemoteSessionStore",
    "build_server",
    "serve",
]
