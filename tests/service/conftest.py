"""Shared fixtures for service tests."""

import pytest

from gway.launchable import Launchable
from gway.service.model import Service
from gway.service.runtime import ProcessBackend


@pytest.fixture
def service_factory(tmp_path):
    """Build service policy around ordinary Gway launchables."""

    def make(
        name="sleeper",
        *,
        project="demo",
        root=None,
        command=None,
        launchable=None,
        **policy,
    ):
        base = tmp_path if root is None else root
        target = launchable or Launchable(
            name=name,
            kind="operation",
            command=command
            or (
                "{python}",
                "-c",
                "import time; time.sleep(30)",
            ),
            root=base,
            target=name,
        )
        return Service(
            project=project,
            name=name,
            root=base,
            launchable=target,
            **policy,
        )

    return make


@pytest.fixture
def process_backend(tmp_path):
    """Return an isolated process backend for service lifecycle tests."""
    return ProcessBackend(state_root=tmp_path / "state")


@pytest.fixture
def running_service(process_backend, service_factory):
    """Start the default sleeper service and always stop it after the test."""
    service = service_factory()
    started = process_backend.start(service)
    try:
        yield service, process_backend, started
    finally:
        process_backend.stop(service)
