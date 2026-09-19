"""Shared fixtures for service tests."""

import pytest

from gway.service.model import Service


@pytest.fixture
def service_factory(tmp_path):
    """Build normalized service definitions with concise overrides."""
    def make(
        name="sleeper",
        *,
        project="demo",
        root=None,
        command=None,
        **kwargs,
    ):
        return Service(
            project=project,
            name=name,
            root=tmp_path if root is None else root,
            command=command or (
                "{python}",
                "-c",
                "import time; time.sleep(30)",
            ),
            **kwargs,
        )

    return make
