from __future__ import annotations

from pathlib import Path

import pytest

import gway.bootstrap as bootstrap
from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry, RegistryError


def test_bootstrap_keeps_upgrade_help_at_cli_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return None

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_lifecycle(["upgrade", "--help"]) is None
    assert calls == []


def test_bootstrap_delegates_upgrade_execution_to_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    class FakeRuntime:
        def execute(self, tokens, *, interactive=False, **kwargs):
            calls.append((list(tokens), interactive))
            return {"status": "skipped", "name": "demo"}

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)
    monkeypatch.setattr(bootstrap, "_render_upgrade_result", lambda result, detail: None)

    assert bootstrap._run_runtime_lifecycle(["-i", "upgrade", "demo"]) == 0
    assert calls == [(["upgrade", "demo"], True)]


@pytest.mark.parametrize(
    "name",
    ["install", "recipe", "result", "store", "uninstall", "upgrade"],
)
def test_registry_reserves_all_runtime_operation_names(tmp_path: Path, name: str) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    project = Project(
        name=name,
        path=tmp_path / name,
        adapter_type="python",
        adapter_config={"module": "example"},
    )

    with pytest.raises(RegistryError, match=rf"reserved GWAY operation: {name}"):
        registry.register(project)
