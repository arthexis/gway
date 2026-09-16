from __future__ import annotations

import os
from pathlib import Path

import pytest

from gway.adapters import AdapterError
from gway.adapters.django import _adapter_environment, _project_context
from gway.project import InstallLayout, Project


def _project(tmp_path: Path, environment: object) -> Project:
    root = tmp_path / "managed"
    checkout = root / "app"
    checkout.mkdir(parents=True)
    return Project(
        name="demo",
        path=checkout,
        adapter_type="django",
        adapter_config={
            "manage": "manage.py",
            "settings": "demo.settings",
            "environment": environment,
        },
        install_layout=InstallLayout(
            root=root,
            checkout=checkout,
            environment=root / ".venv",
        ),
    )


def test_django_adapter_environment_expands_managed_paths_and_restores_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(
        tmp_path,
        {
            "ARTHEXIS_MODE": "installed",
            "ARTHEXIS_DATA_DIR": "{root}/var/lib",
            "PROJECT_CHECKOUT": "{project}",
            "PROJECT_ENVIRONMENT": "{environment}",
            "SCALAR": 7,
        },
    )
    monkeypatch.setenv("ARTHEXIS_MODE", "outside")
    monkeypatch.delenv("ARTHEXIS_DATA_DIR", raising=False)

    resolved = _adapter_environment(project)
    assert resolved["ARTHEXIS_DATA_DIR"] == str(tmp_path / "managed" / "var" / "lib")
    assert resolved["PROJECT_CHECKOUT"] == str(tmp_path / "managed" / "app")
    assert resolved["PROJECT_ENVIRONMENT"] == str(tmp_path / "managed" / ".venv")
    assert resolved["SCALAR"] == "7"

    with _project_context(project, "demo.settings"):
        assert os.environ["ARTHEXIS_MODE"] == "installed"
        assert os.environ["ARTHEXIS_DATA_DIR"] == resolved["ARTHEXIS_DATA_DIR"]
        assert os.environ["DJANGO_SETTINGS_MODULE"] == "demo.settings"

    assert os.environ["ARTHEXIS_MODE"] == "outside"
    assert "ARTHEXIS_DATA_DIR" not in os.environ
    assert os.environ.get("DJANGO_SETTINGS_MODULE") != "demo.settings"


def test_django_adapter_environment_rejects_non_scalar_values(tmp_path: Path) -> None:
    project = _project(tmp_path, {"BROKEN": ["not", "scalar"]})
    with pytest.raises(AdapterError, match="environment must be a table of scalar values"):
        _adapter_environment(project)
