from __future__ import annotations

from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.project import Project
from gway.service import ServiceError, ServiceManager, attach_environment_files, detach_environment_files
from gway.service.attachments import service_environment_files


def _paths(tmp_path: Path) -> GwayPaths:
    return GwayPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "app"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "app"
aliases = ["app-alias"]

[adapter]
type = "python"
module = "app"

[services.web]
command = ["/bin/true"]

[services.worker]
command = ["/bin/true"]
""",
        encoding="utf-8",
    )
    return Project.from_path(root)


def test_generic_environment_attachment_renders_for_all_project_services(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    environment = tmp_path / "provider.env"
    environment.write_text('PROVIDER="fixture"\n', encoding="utf-8")

    attach_environment_files(
        project.name,
        owner="fixture",
        environment_files=[environment],
        paths=_paths(tmp_path),
    )

    web = ServiceManager(
        project,
        service="web",
        unit_directory=tmp_path / "systemd",
    ).render(user="root")
    worker = ServiceManager(
        project,
        service="worker",
        unit_directory=tmp_path / "systemd",
    ).render(user="root")

    expected = f'EnvironmentFile="{environment}"'
    assert expected in web
    assert expected in worker


def test_service_specific_attachment_is_scoped_and_alias_aware(tmp_path: Path) -> None:
    project = _project(tmp_path)
    environment = tmp_path / "worker.env"
    environment.write_text("WORKER=1\n", encoding="utf-8")
    paths = _paths(tmp_path)

    attach_environment_files(
        "app-alias",
        owner="fixture",
        environment_files=[environment],
        service="worker",
        paths=paths,
    )

    assert service_environment_files(project, "web") == ()
    assert service_environment_files(project, "worker") == (environment,)


def test_detaching_environment_files_removes_provider_attachment(tmp_path: Path) -> None:
    project = _project(tmp_path)
    environment = tmp_path / "provider.env"
    environment.write_text("VALUE=1\n", encoding="utf-8")
    paths = _paths(tmp_path)

    attach_environment_files(
        project.name,
        owner="fixture",
        environment_files=[environment],
        paths=paths,
    )
    detach_environment_files(project.name, owner="fixture", paths=paths)

    assert service_environment_files(project, "web") == ()


def test_attachment_environment_path_rejects_nul(tmp_path: Path) -> None:
    with pytest.raises(ServiceError, match="NUL"):
        attach_environment_files(
            "app",
            owner="fixture",
            environment_files=[Path("/tmp/provider\0.env")],
            paths=_paths(tmp_path),
        )
