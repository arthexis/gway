from __future__ import annotations

from pathlib import Path

import pytest

from gway.install_extras import InstallExtraSelector
from gway.project import ManifestError, Project
from gway.runner import Runner


MANIFEST = """[project]
name = "arthexis"

[adapter]
type = "django"

[install]
root = "/opt/arthexis"
checkout = "app"
environment = ".venv"

[install.extras]
argument = "--role"
default = "Terminal"
state = ".locks/role.lck"

[install.extras.values]
Control = ["celery"]
Satellite = ["celery"]
Terminal = []
Watchtower = ["celery"]
"""


def _project(tmp_path: Path, *, environment: Path | None = None) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "gway.toml").write_text(MANIFEST, encoding="utf-8")
    project = Project.from_path(tmp_path)
    if environment is None:
        return project
    return Project(
        name=project.name,
        path=project.path,
        adapter_type=project.adapter_type,
        adapter_config=project.adapter_config,
        environment=environment,
        install_layout=project.install_layout,
    )


def test_selector_defaults_to_terminal_and_persists_explicit_role(tmp_path: Path) -> None:
    project = _project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None

    default = selector.resolve(project, ())
    assert default.value == "Terminal"
    assert default.extras == ()

    control = selector.resolve(project, ("--role", "control"))
    assert control.value == "Control"
    assert control.extras == ("celery",)
    selector.persist(project, control.value)

    preserved = selector.resolve(project, ())
    assert preserved.value == "Control"
    assert preserved.extras == ("celery",)


def test_selector_rejects_unknown_role(tmp_path: Path) -> None:
    project = _project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None

    with pytest.raises(ManifestError, match="invalid --role value"):
        selector.resolve(project, ("--role", "Unknown"))


def test_refresh_rebuilds_environment_when_role_changes_extra_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = tmp_path / "venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    project = _project(tmp_path / "project", environment=environment)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Control")

    runner = Runner()
    captured: dict[str, object] = {}

    def fake_prepare(project_arg, *, arguments=()):
        captured["project"] = project_arg
        captured["arguments"] = tuple(arguments)
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    monkeypatch.setattr(runner, "prepare", fake_prepare)

    assert runner.refresh(project, arguments=("--role", "Terminal")) == environment
    assert captured["arguments"] == ("--role", "Terminal")


def test_refresh_keeps_environment_when_roles_share_same_extra_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = tmp_path / "venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    project = _project(tmp_path / "project", environment=environment)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Control")

    runner = Runner()
    captured: dict[str, object] = {}

    def fake_install(project_arg, environment_arg, *, upgrade, extras=()):
        captured["upgrade"] = upgrade
        captured["extras"] = tuple(extras)

    monkeypatch.setattr(runner, "_install_project", fake_install)

    assert runner.refresh(project, arguments=("--role", "Satellite")) == environment
    assert captured == {"upgrade": True, "extras": ("celery",)}
    assert selector.current(project) == "Satellite"
