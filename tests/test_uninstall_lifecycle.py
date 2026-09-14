from __future__ import annotations

from pathlib import Path

from gway.config import GwayPaths
from gway.install import Installer
from gway.project import LifecycleHooks, Project
from gway.registry import Registry


def _project(tmp_path: Path) -> tuple[Registry, Project]:
    checkout = tmp_path / "app"
    environment = tmp_path / ".venv"
    checkout.mkdir()
    environment.mkdir()
    (checkout / "gway.toml").write_text(
        """[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture"

[lifecycle]
uninstall = "fixture.lifecycle:uninstall"
""",
        encoding="utf-8",
    )
    project = Project(
        name="fixture",
        path=checkout,
        adapter_type="python",
        adapter_config={"module": "fixture"},
        repository="arthexis/gway-fixture",
        environment=environment,
        lifecycle_hooks=LifecycleHooks(uninstall="fixture.lifecycle:uninstall"),
    )
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(project)
    return registry, project


def test_manifest_accepts_uninstall_only_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture"

[lifecycle]
uninstall = "fixture.lifecycle:uninstall"
""",
        encoding="utf-8",
    )

    project = Project.from_path(root)

    assert project.lifecycle_hooks == LifecycleHooks(
        uninstall="fixture.lifecycle:uninstall"
    )


def test_managed_uninstall_stops_services_then_runs_hook_before_removal(
    monkeypatch, tmp_path: Path
) -> None:
    registry, project = _project(tmp_path)
    calls: list[object] = []

    class FakeServices:
        def __init__(self, selected: Project) -> None:
            assert selected == project

        def uninstall(self) -> None:
            calls.append("services")

    class FakeRunner:
        def environment_path(self, selected: Project) -> Path:
            return project.environment

        def run_lifecycle(self, selected: Project, action: str) -> None:
            assert selected == project
            assert project.path.exists()
            assert project.environment is not None and project.environment.exists()
            calls.append(("hook", action))

    monkeypatch.setattr("gway.install.ServiceManager", FakeServices)
    installer = Installer(registry, runner=FakeRunner())

    removed = installer.uninstall("fixture")

    assert removed == project
    assert calls == ["services", ("hook", "uninstall")]
    assert not project.path.exists()
    assert project.environment is not None and not project.environment.exists()
    assert registry.get("fixture") is None


def test_failed_uninstall_hook_keeps_checkout_environment_and_registration(
    monkeypatch, tmp_path: Path
) -> None:
    registry, project = _project(tmp_path)

    class FakeServices:
        def __init__(self, selected: Project) -> None:
            pass

        def uninstall(self) -> None:
            pass

    class FakeRunner:
        def environment_path(self, selected: Project) -> Path:
            return project.environment

        def run_lifecycle(self, selected: Project, action: str) -> None:
            raise RuntimeError("hook failed")

    monkeypatch.setattr("gway.install.ServiceManager", FakeServices)
    installer = Installer(registry, runner=FakeRunner())

    try:
        installer.uninstall("fixture")
    except RuntimeError as exc:
        assert str(exc) == "hook failed"
    else:
        raise AssertionError("uninstall should fail")

    assert project.path.exists()
    assert project.environment is not None and project.environment.exists()
    assert registry.require("fixture") == project
