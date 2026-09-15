from __future__ import annotations

from pathlib import Path

import pytest

from gway import service
from gway.project import Project


def _project(tmp_path: Path, *, service_lines: str = "") -> Project:
    root = tmp_path / "web"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "web"

[adapter]
type = "python"
module = "gway_web.commands"

[services.api]
command = ["{python}", "-m", "gway_web.api_service"]
"""
        + service_lines,
        encoding="utf-8",
    )
    return Project.from_path(root)


def test_service_render_pins_active_gway_paths(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "system-config"
    data_home = tmp_path / "system-data"
    monkeypatch.setenv("GWAY_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("GWAY_DATA_HOME", str(data_home))

    manager = service.ServiceManager(
        _project(tmp_path),
        service="api",
        unit_directory=tmp_path / "systemd",
    )

    unit = manager.render(user="root")

    assert f'Environment="GWAY_CONFIG_HOME={config_home}"' in unit
    assert f'Environment="GWAY_DATA_HOME={data_home}"' in unit


def test_service_environment_can_override_runtime_path(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "system-config"
    data_home = tmp_path / "system-data"
    custom_data_home = tmp_path / "custom-data"
    monkeypatch.setenv("GWAY_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("GWAY_DATA_HOME", str(data_home))
    project = _project(
        tmp_path,
        service_lines=(
            "\n[services.api.environment]\n"
            f'GWAY_DATA_HOME = "{custom_data_home}"\n'
        ),
    )

    unit = service.ServiceManager(
        project,
        service="api",
        unit_directory=tmp_path / "systemd",
    ).render(user="root")

    assert f'Environment="GWAY_CONFIG_HOME={config_home}"' in unit
    assert f'Environment="GWAY_DATA_HOME={custom_data_home}"' in unit
    assert f'Environment="GWAY_DATA_HOME={data_home}"' not in unit


def test_invalid_service_environment_keeps_existing_validation(tmp_path: Path) -> None:
    project = _project(tmp_path, service_lines='environment = "invalid"\n')
    manager = service.ServiceManager(
        project,
        service="api",
        unit_directory=tmp_path / "systemd",
    )

    with pytest.raises(service.ServiceError, match="environment must be a table"):
        manager.render(user="root")
