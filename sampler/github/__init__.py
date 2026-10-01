"""Maintained GitHub capability discovered through the sampler route."""

from __future__ import annotations

from gway.ingestion.python import ingest_python

from .github import Client, GitHubError, GitHubResponse, RateLimit
from .status import Controller
from .githubops import ADMIN_OPERATIONS, WRITE_OPERATIONS


def _classify(gateway):
    """Apply GitHub source/read/write/admin metadata to registered operations."""
    for record in gateway.ops.records():
        if not record.name.startswith("github."):
            continue
        operation = record.name.removeprefix("github.")
        access = "write" if operation in WRITE_OPERATIONS else "read"
        metadata = dict(getattr(record.callable, "__gway_metadata__", {}) or {})
        topics = (*metadata.get("topics", ()), "github", "source", access)
        if operation in ADMIN_OPERATIONS:
            topics = (*topics, "admin")
        metadata["topics"] = tuple(dict.fromkeys(topics))
        record.callable.__gway_metadata__ = metadata
        record.callable.mutates = access == "write"
        record.callable.__gway_mutates__ = record.callable.mutates
        if access == "read":
            record.callable.__gway_supports_no_mutate__ = True


def register(gateway, *, client=None):
    """Register the maintained GitHub capability on one Gateway.

    GitHub is intentionally a sampler capability rather than a Gateway builtin.
    The sampler removes its own filesystem root from the semantic route, so this
    package publishes the same ``github.*`` command surface as the former manual
    Gateway ingestion point.
    """
    existing = getattr(gateway, "_github_controller", None)
    if existing is not None and client is None:
        return existing

    controller = Controller(gateway, client=client)
    gateway._github_controller = controller
    ingest_python(gateway, controller, path=("github",))
    _classify(gateway)
    return controller


__all__ = [
    "ADMIN_OPERATIONS",
    "Client",
    "Controller",
    "GitHubError",
    "GitHubResponse",
    "RateLimit",
    "WRITE_OPERATIONS",
    "register",
]
