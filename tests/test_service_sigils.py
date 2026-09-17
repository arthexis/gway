from __future__ import annotations

from pathlib import Path

import pytest

from gway import service
from gway.project import Project


def _project(tmp_path: Path, manifest: str) -> Project:
    root = tmp_path / "semantic-service"
    root.mkdir()
    (root / "gway.toml").write_text(manifest, encoding="utf-8")
    return Project.from_path(root)


def test_service_command_and_environment_resolve_semantic_variables(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[variables.logs]
source = "/var/lib/gway/runs"

[variables.repo]
endpoint = "https://manifest.example"

[services.logs]
command = ["echo", "[logs.source]"]

[services.logs.environment]
REPO_ENDPOINT = "[repo.endpoint]"
""",
    )

    unit = service.ServiceManager(
        project,
        service="logs",
        unit_directory=tmp_path / "systemd",
    ).render(user="display")

    assert "/var/lib/gway/runs" in unit
    assert "https://manifest.example" in unit
    assert "[logs.source]" not in unit
    assert "[repo.endpoint]" not in unit


def test_service_semantic_variable_uses_gway_environment_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[variables.logs]
source = "/var/lib/gway/runs"

[services.logs]
command = ["echo", "[logs.source]"]
""",
    )
    monkeypatch.setenv("GWAY_LOGS_SOURCE", "/opt/gway/runs")

    unit = service.ServiceManager(
        project,
        service="logs",
        unit_directory=tmp_path / "systemd",
    ).render(user="display")

    assert "/opt/gway/runs" in unit
    assert "/var/lib/gway/runs" not in unit


def test_service_sigil_uses_inline_fallback(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[variables]
default_logs_source = "/tmp/gway-runs"

[services.logs]
command = ["echo", "[logs.source|default_logs_source]"]
""",
    )

    unit = service.ServiceManager(
        project,
        service="logs",
        unit_directory=tmp_path / "systemd",
    ).render(user="display")

    assert "/tmp/gway-runs" in unit
    assert "[logs.source" not in unit


def test_unresolved_service_sigil_fails_before_existing_unit_is_replaced(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[services.logs]
command = ["echo", "[logs.source]"]
""",
    )
    unit_directory = tmp_path / "systemd"
    unit_directory.mkdir()
    existing = unit_directory / "gway-semantic-service-logs.service"
    existing.write_text("existing unit\n", encoding="utf-8")

    with pytest.raises(service.ServiceError, match="unresolved Sigil"):
        service.ServiceManager(
            project,
            service="logs",
            unit_directory=unit_directory,
        )

    assert existing.read_text(encoding="utf-8") == "existing unit\n"


def test_explicit_service_selection_does_not_resolve_unselected_service(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[variables.good]
value = "ready"

[services.good]
command = ["echo", "[good.value]"]

[services.bad]
command = ["echo", "[missing.value]"]
""",
    )

    unit = service.ServiceManager(
        project,
        service="good",
        unit_directory=tmp_path / "systemd",
    ).render(user="display")

    assert "ready" in unit
    assert "[missing.value]" not in unit


def test_service_placeholders_still_expand_after_sigil_resolution(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        """[project]
name = "semantic-service"

[adapter]
type = "python"
module = "semantic_service.commands"

[variables.config]
name = "worker.toml"

[services.worker]
command = ["{python}", "{project}/[config.name]"]
""",
    )

    unit = service.ServiceManager(
        project,
        service="worker",
        unit_directory=tmp_path / "systemd",
    ).render(user="display")

    assert str(project.path / "worker.toml") in unit
    assert "{project}" not in unit
    assert "[config.name]" not in unit
