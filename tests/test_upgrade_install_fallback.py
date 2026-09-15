from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import gway.cli as cli
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry, RegistryError
from gway.runtime import GwayRuntime
from gway.upgrade import UpgradeResult, Upgrader


def _project(tmp_path: Path, name: str = "fixture") -> Project:
    return Project(
        name=name,
        path=tmp_path / name,
        adapter_type="python",
        adapter_config={"module": f"{name}.gway"},
        repository=f"arthexis/gway-{name}",
        revision="installed-revision",
    )


def test_upgrade_install_falls_back_only_when_project_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    repositories = object()
    runner = object()
    installed = _project(tmp_path)
    calls: list[tuple[object, ...]] = []

    class FakeInstaller:
        def __init__(self, selected_registry, selected_repositories, selected_runner) -> None:
            assert selected_registry is registry
            assert selected_repositories is repositories
            assert selected_runner is runner

        def install(self, name: str, *, arguments=(), clean=True) -> Project:
            calls.append((name, tuple(arguments), clean))
            return installed

    monkeypatch.setattr("gway.upgrade.Installer", FakeInstaller)
    result = Upgrader(
        registry,
        repositories=repositories,
        runner=runner,
    ).project_result(
        "fixture",
        install=True,
        arguments=("--role", "Watchtower"),
    )

    assert result == UpgradeResult(installed, changed=True, installed=True)
    assert calls == [("fixture", ("--role", "Watchtower"), True)]


def test_upgrade_missing_project_stays_strict_without_install(tmp_path: Path) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)

    with pytest.raises(RegistryError, match="project is not registered: fixture"):
        Upgrader(
            registry,
            repositories=object(),
            runner=object(),
        ).project_result("fixture")


def test_cli_upgrade_install_uses_passthrough_flag_for_single_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    installed = _project(tmp_path)
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeInstaller:
        def __init__(self, selected_registry, repositories, runner) -> None:
            assert selected_registry is registry

        def install(self, name: str, *, arguments=(), clean=True) -> Project:
            calls.append((name, tuple(arguments)))
            return installed

    monkeypatch.setattr("gway.upgrade.Installer", FakeInstaller)
    dispatcher = SimpleNamespace(registry=registry)

    assert (
        cli.main(
            ["upgrade", "fixture", "--install", "--role", "Watchtower"],
            dispatcher=dispatcher,
        )
        == 0
    )
    capsys.readouterr()
    assert calls == [("fixture", ("--role", "Watchtower"))]


def test_runtime_upgrade_install_service_preserves_recipe_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    dispatcher = Dispatcher(registry=registry)
    project = _project(tmp_path)
    calls: list[tuple[object, ...]] = []

    class FakeUpgrader:
        def __init__(self, selected_registry) -> None:
            assert selected_registry is registry

        def project_result(
            self,
            name: str,
            *,
            force: bool = False,
            reload: bool = False,
            install: bool = False,
            arguments=(),
        ) -> UpgradeResult:
            calls.append((name, force, reload, install, tuple(arguments)))
            return UpgradeResult(project, changed=True, installed=True)

    monkeypatch.setattr("gway.runtime.Upgrader", FakeUpgrader)
    monkeypatch.setattr(
        "gway.runtime._base._install_project_service",
        lambda selected: {"status": "installed", "project": selected.name},
    )

    result = GwayRuntime(dispatcher).execute(
        [
            "upgrade",
            "fixture",
            "--install",
            "--service",
            "--role",
            "Watchtower",
        ]
    )

    assert result["status"] == "installed"
    assert result["service"] == {"status": "installed", "project": "fixture"}
    assert calls == [("fixture", False, False, True, ("--role", "Watchtower"))]
