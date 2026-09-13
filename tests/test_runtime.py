from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.errors import DispatchError
from gway.explain import explain_scope
from gway.project import Project
from gway.recipe import RecipeSession
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "runtime-project"
    root.mkdir()
    (root / "runtime_commands.py").write_text(
        """def status() -> dict[str, str]:
    return {"status": "ok"}


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("runtime_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "runtime_commands"},
        )
    )
    return Dispatcher(registry)


def _managed_project(tmp_path: Path, name: str = "fixture") -> Project:
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    return Project(name=name, path=root, adapter_type="python", adapter_config={"module": "unused"})


def test_runtime_executes_managed_statement(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    assert runtime.execute(["demo", "status"]) == {"status": "ok"}


def test_runtime_preserves_chain_transfer(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    assert runtime.execute(["demo", "echo", "alpha", "-", "demo", "echo"]) == "alpha"


def test_recipe_session_uses_same_runtime_for_store_and_managed_commands(tmp_path: Path) -> None:
    session = RecipeSession(_dispatcher(tmp_path))

    assert session.run(["store", "--value", "alpha"]) == {"value": "alpha"}
    assert session.run(["demo", "echo", "[value]"]) == "alpha"


def test_runtime_install_publishes_core_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    project = _managed_project(tmp_path, "installed")
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeInstaller:
        def __init__(self, registry) -> None:
            assert registry is dispatcher.registry

        def install(self, spec: str, *, arguments=()):
            calls.append((spec, tuple(arguments)))
            return project

    monkeypatch.setattr("gway.runtime.Installer", FakeInstaller)
    runtime = GwayRuntime(dispatcher)
    context: dict[str, object] = {}

    result = runtime.execute(["install", "fixture", "--", "--mode", "safe"], context=context)

    assert result["status"] == "installed"
    assert result["name"] == "installed"
    assert calls == [("fixture", ("--", "--mode", "safe"))]
    assert context["status"] == "installed"
    assert context["name"] == "installed"
    assert context["result"] == result


def test_runtime_uninstall_uses_installer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    project = _managed_project(tmp_path, "removed")

    class FakeInstaller:
        def __init__(self, registry) -> None:
            assert registry is dispatcher.registry

        def uninstall(self, name: str):
            assert name == "legacy-name"
            return project

    monkeypatch.setattr("gway.runtime.Installer", FakeInstaller)

    result = GwayRuntime(dispatcher).execute(["uninstall", "legacy-name"])

    assert result["status"] == "uninstalled"
    assert result["name"] == "removed"


def test_runtime_upgrade_specific_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    project = _managed_project(tmp_path, "upgraded")
    calls: list[tuple[str, bool, bool, tuple[str, ...]]] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            assert registry is dispatcher.registry

        def project_result(self, name, *, force=False, reload=False, arguments=()):
            calls.append((name, force, reload, tuple(arguments)))
            return SimpleNamespace(changed=True, project=project)

    monkeypatch.setattr("gway.runtime.Upgrader", FakeUpgrader)

    result = GwayRuntime(dispatcher).execute(["upgrade", "fixture", "--force"])

    assert result["status"] == "upgraded"
    assert result["name"] == "upgraded"
    assert calls == [("fixture", True, False, ())]


def test_core_operation_rejects_incoming_chain_value(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with pytest.raises(DispatchError, match="uninstall cannot receive chain positionals"):
        runtime.execute(["demo", "echo", "fixture", "-", "uninstall", "fixture"])


def test_runtime_emits_operation_provenance(tmp_path: Path) -> None:
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with explain_scope() as trace:
        runtime.execute(["demo", "status"])

    kinds = [step.kind for step in trace]
    assert "runtime.operation.start" in kinds
    assert "runtime.operation.result" in kinds
