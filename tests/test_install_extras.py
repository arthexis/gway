from pathlib import Path

from gway.install_extras import InstallExtraSelector
from gway.project import ManifestError, Project
from gway.runner import Runner

MANIFEST = """[project]
name = "arthexis"

[adapter]
type = "django"

[install]
root = "{root}"
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

MANIFEST_WITHOUT_EXTRAS = """[project]
name = "arthexis"

[adapter]
type = "django"

[install]
root = "{root}"
checkout = "app"
environment = ".venv"
"""


def _manifest(tmp_path: Path, template: str = MANIFEST) -> str:
    root = tmp_path.parent / f"{tmp_path.name}-install-root"
    return template.format(root=root.as_posix())


def _project(tmp_path: Path, *, environment: Path | None = None) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "gway.toml").write_text(_manifest(tmp_path), encoding="utf-8")
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
    assert selector.state_path(project).is_relative_to(project.install_layout.root)
    assert not selector.state_path(project).is_relative_to(project.path)


def test_selector_rejects_unknown_role(tmp_path: Path) -> None:
    project = _project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None

    try:
        selector.resolve(project, ("--role", "Unknown"))
    except ManifestError as exc:
        assert "invalid --role value" in str(exc)
    else:
        raise AssertionError("expected ManifestError")


def test_selector_rejects_explicit_empty_role(tmp_path: Path) -> None:
    project = _project(tmp_path)
    selector = InstallExtraSelector.from_project(project)
    assert selector is not None
    selector.persist(project, "Control")

    for arguments in (("--role", ""), ("--role=",)):
        try:
            selector.resolve(project, arguments)
        except ManifestError as exc:
            assert "invalid --role value" in str(exc)
        else:
            raise AssertionError("expected ManifestError")


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
    runner._write_managed_extras(environment, ("celery",))
    captured: dict[str, object] = {}

    def fake_prepare(project_arg, *, arguments=()):
        captured["project"] = project_arg
        captured["arguments"] = tuple(arguments)
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    monkeypatch.setattr(runner, "prepare", fake_prepare)

    assert runner.refresh(project, arguments=("--role", "Terminal")) == environment
    assert captured["arguments"] == ("--role", "Terminal")


def test_refresh_rebuilds_legacy_environment_without_extras_marker(
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
    selector.persist(project, "Terminal")

    runner = Runner()
    rebuilt: list[tuple[str, ...]] = []

    def fake_prepare(project_arg, *, arguments=()):
        rebuilt.append(tuple(arguments))
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    monkeypatch.setattr(runner, "prepare", fake_prepare)

    assert runner.refresh(project) == environment
    assert rebuilt == [()]


def test_refresh_rebuilds_when_manifest_removes_extras_selector(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment = tmp_path / "venv"
    python = environment / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    project_path = tmp_path / "project"
    _project(project_path, environment=environment)

    runner = Runner()
    runner._write_managed_extras(environment, ("celery",))
    (project_path / "gway.toml").write_text(
        _manifest(project_path, MANIFEST_WITHOUT_EXTRAS),
        encoding="utf-8",
    )
    refreshed = Project.from_path(project_path)
    refreshed = Project(
        name=refreshed.name,
        path=refreshed.path,
        adapter_type=refreshed.adapter_type,
        adapter_config=refreshed.adapter_config,
        environment=environment,
        install_layout=refreshed.install_layout,
    )
    rebuilt: list[tuple[str, ...]] = []

    def fake_prepare(project_arg, *, arguments=()):
        rebuilt.append(tuple(arguments))
        environment.mkdir(parents=True, exist_ok=True)
        return environment

    monkeypatch.setattr(runner, "prepare", fake_prepare)

    assert runner.refresh(refreshed) == environment
    assert rebuilt == [()]


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
    runner._write_managed_extras(environment, ("celery",))
    captured: dict[str, object] = {}

    def fake_install(project_arg, environment_arg, *, upgrade, extras=()):
        captured["upgrade"] = upgrade
        captured["extras"] = tuple(extras)

    monkeypatch.setattr(runner, "_install_project", fake_install)

    assert runner.refresh(project, arguments=("--role", "Satellite")) == environment
    assert captured == {"upgrade": True, "extras": ("celery",)}
    assert selector.current(project) == "Satellite"
