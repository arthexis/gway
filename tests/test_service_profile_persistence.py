from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.runner as runner_module
from gway import service
from gway.install_extras import InstallExtraSelector
from gway.project import Project
from gway.runner import Runner


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "app"
    root.mkdir()
    (root / "gway.toml").write_text(
        f'''[project]
name = "example"

[adapter]
type = "python"
module = "example.gway"

[install]
root = "{tmp_path}"
checkout = "app"
environment = ".venv"

[lifecycle]
install = "example.lifecycle:install"
upgrade = "example.lifecycle:upgrade"

[service_profile]
argument = "--role"
default = "Terminal"
values = ["Control", "Satellite", "Terminal", "Watchtower"]

[services.web-local]
command = ["{{python}}", "manage.py", "runserver"]
profiles = ["Terminal", "Watchtower"]

[services.web-edge]
command = ["{{python}}", "manage.py", "runserver"]
profiles = ["Control", "Satellite"]

[services.worker]
command = ["{{python}}", "-m", "example.worker"]
profiles = ["Control", "Satellite", "Watchtower"]
''',
        encoding="utf-8",
    )
    return Project.from_path(root)


def test_service_profile_selector_persists_without_package_extras(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    selector = InstallExtraSelector.from_project(project)

    assert selector is not None
    assert selector.service_profile is True
    selection = selector.resolve(project, ("--role", "Watchtower"))
    assert selection.value == "Watchtower"
    assert selection.extras == ()

    selector.persist(project, selection.value)

    assert (tmp_path / ".gway" / "service-profile").read_text(encoding="utf-8") == (
        "Watchtower\n"
    )
    assert selector.resolve(project, ()).value == "Watchtower"


def test_persisted_service_profile_selects_later_service_topology(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Watchtower")

    manager = service.ServiceManager(project, unit_directory=tmp_path / "systemd")

    assert manager.active_profile == "Watchtower"
    assert manager.unit_names == [
        "gway-example-web-local.service",
        "gway-example-worker.service",
    ]


def test_lifecycle_receives_persisted_service_profile(monkeypatch, tmp_path: Path) -> None:
    project = make_project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Watchtower")

    environment = tmp_path / ".venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    project = Project.from_path(project.path)

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    Runner().run_lifecycle(project, "install")

    env = captured["kwargs"]["env"]
    assert env["GWAY_SERVICE_PROFILE"] == "Watchtower"


def test_lifecycle_argument_overrides_previous_profile(monkeypatch, tmp_path: Path) -> None:
    project = make_project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Terminal")

    environment = tmp_path / ".venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)

    Runner().run_lifecycle(project, "install", ["--role", "Watchtower"])

    env = captured["kwargs"]["env"]
    assert env["GWAY_SERVICE_PROFILE"] == "Watchtower"
