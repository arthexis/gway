from __future__ import annotations

import sys
from pathlib import Path

from gway.adapters.django import _environment_site_packages, _project_context
from gway.project import Project


def test_project_context_prefers_checkout_over_managed_site_packages(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    environment = tmp_path / ".venv"
    site_packages = _environment_site_packages(environment)
    site_packages.mkdir(parents=True)

    project = Project(
        name="demo",
        path=project_path,
        adapter_type="django",
        adapter_config={},
        environment=environment,
    )

    project_value = str(project_path)
    site_value = str(site_packages)
    assert project_value not in sys.path
    assert site_value not in sys.path

    with _project_context(project, None):
        assert sys.path.index(project_value) < sys.path.index(site_value)

    assert project_value not in sys.path
    assert site_value not in sys.path
