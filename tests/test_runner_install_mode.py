from pathlib import Path

from gway.project import Project
from gway.runner import Runner

MANIFEST = """[project]
name = "example"

[adapter]
type = "python"
module = "example"
"""


def test_managed_project_install_is_editable(tmp_path: Path, monkeypatch) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    project = Project.from_path(project_path)
    environment = tmp_path / "venv"

    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(list(command))

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)

    Runner()._install_project(project, environment, upgrade=False)

    assert captured == [
        [
            str(Runner.environment_python(environment)),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            str(project.path),
        ]
    ]


def test_managed_project_refresh_keeps_extras_in_editable_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    project = Project.from_path(project_path)
    environment = tmp_path / "venv"

    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(list(command))

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)

    Runner()._install_project(project, environment, upgrade=True, extras=("celery",))

    command = captured[0]
    assert "--upgrade" in command
    assert "-e" in command
    assert command[-1] == f"{project.path}[celery]"
