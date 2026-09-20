"""Shared fixtures for service tests."""

import pytest

from gway.launchable import Launchable
from gway.service.model import Service


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
            command=command or (
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
