from pathlib import Path

import pytest

from gway.project import Project
from gway.service import ServiceError, ServiceManager


@pytest.fixture(autouse=True)
def _clear_service_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GWAY_SERVICE", raising=False)
    monkeypatch.delenv("GWAY_SERVICE_PROFILE", raising=False)


def _project(tmp_path: Path, profile_file: str = ".locks/role.lck") -> Project:
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        f'''[project]\nname = "arthexis"\nservice_profile_file = "{profile_file}"\n\n[adapter]\ntype = "python"\nmodule = "example"\n\n[services.web-local]\ncommand = ["python", "-m", "example.local"]\nprofiles = ["Terminal", "Watchtower"]\n\n[services.web-edge]\ncommand = ["python", "-m", "example.edge"]\nprofiles = ["Control", "Satellite"]\n\n[services.worker]\ncommand = ["python", "-m", "example.worker"]\nprofiles = ["Control", "Satellite", "Watchtower"]\n''',
        encoding="utf-8",
    )
    return Project.from_path(tmp_path)


def _write_role(tmp_path: Path, role: str) -> None:
    role_file = tmp_path / ".locks" / "role.lck"
    role_file.parent.mkdir(parents=True, exist_ok=True)
    role_file.write_text(f"{role}\n", encoding="utf-8")


def test_project_profile_file_selects_watchtower_services(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_role(tmp_path, "Watchtower")

    manager = ServiceManager(project)

    assert manager.active_profile == "Watchtower"
    assert manager.unit_names == [
        "gway-arthexis-web-local.service",
        "gway-arthexis-worker.service",
    ]


def test_project_profile_file_selects_edge_services(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_role(tmp_path, "Satellite")

    manager = ServiceManager(project)

    assert manager.active_profile == "Satellite"
    assert manager.unit_names == [
        "gway-arthexis-web-edge.service",
        "gway-arthexis-worker.service",
    ]


def test_explicit_profile_overrides_project_profile_file(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_role(tmp_path, "Watchtower")

    manager = ServiceManager(project, profile="Control")

    assert manager.active_profile == "Control"
    assert manager.unit_names == [
        "gway-arthexis-web-edge.service",
        "gway-arthexis-worker.service",
    ]


def test_explicit_service_bypasses_missing_project_profile_file(tmp_path: Path) -> None:
    project = _project(tmp_path)

    manager = ServiceManager(project, service="web-local")

    assert manager.active_profile is None
    assert manager.unit_name == "gway-arthexis-web-local.service"


def test_missing_configured_project_profile_file_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path)

    with pytest.raises(ServiceError, match="cannot read configured service profile file"):
        ServiceManager(project)


def test_all_services_bypasses_missing_project_profile_file(tmp_path: Path) -> None:
    project = _project(tmp_path)

    manager = ServiceManager(project, all_services=True)

    assert manager.active_profile is None
    assert manager.unit_names == [
        "gway-arthexis-web-local.service",
        "gway-arthexis-web-edge.service",
        "gway-arthexis-worker.service",
    ]
