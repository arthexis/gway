from pathlib import Path

from gway import service
from gway.project import Project


def test_selected_profile_is_exposed_to_service_runtime(tmp_path: Path) -> None:
    project_dir = tmp_path / "example"
    project_dir.mkdir()
    (project_dir / "gway.toml").write_text(
        """[project]
name = "example"

[adapter]
type = "python"
module = "example"

[services.web]
command = ["python", "-m", "example"]
profiles = ["Control", "Terminal"]
""",
        encoding="utf-8",
    )

    manager = service.ServiceManager(Project.from_path(project_dir), profile="Control")

    assert 'Environment="GWAY_SERVICE_PROFILE=Control"' in manager.render(user="example")


def test_manifest_can_explicitly_override_profile_environment(tmp_path: Path) -> None:
    project_dir = tmp_path / "example"
    project_dir.mkdir()
    (project_dir / "gway.toml").write_text(
        """[project]
name = "example"

[adapter]
type = "python"
module = "example"

[services.web]
command = ["python", "-m", "example"]
profiles = ["Control"]

[services.web.environment]
GWAY_SERVICE_PROFILE = "Custom"
""",
        encoding="utf-8",
    )

    manager = service.ServiceManager(Project.from_path(project_dir), profile="Control")

    rendered = manager.render(user="example")
    assert 'Environment="GWAY_SERVICE_PROFILE=Custom"' in rendered
    assert 'Environment="GWAY_SERVICE_PROFILE=Control"' not in rendered
