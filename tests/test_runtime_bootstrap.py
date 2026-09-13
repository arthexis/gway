from __future__ import annotations

from pathlib import Path

import pytest

import gway.bootstrap as bootstrap
from gway.config import GwayPaths
from gway.project import Project
from gway.registry import Registry, RegistryError
from gway.upgrade import UpgradeError


def test_bootstrap_keeps_upgrade_help_at_cli_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return None

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_lifecycle(["upgrade", "--help"]) is None
    assert calls == []


def test_bootstrap_respects_literal_boundary_for_lifecycle_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return {"status": "installed", "name": "demo"}

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_lifecycle(["install", "demo", "--", "--help"]) == 0
    assert calls == [["install", "demo", "--", "--help"]]


def test_bootstrap_uninstall_help_is_detected_before_literal_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return None

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_lifecycle(["uninstall", "demo", "--help"]) == 0
    assert calls == []
    assert "Uninstall a registered project" in capsys.readouterr().out


def test_bootstrap_recipe_help_stays_at_cli_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return None

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_recipe(["recipe", "--help"]) is None
    assert calls == []


def test_bootstrap_downstream_help_remains_in_recipe_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, **kwargs):
            calls.append(list(tokens))
            return None

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    args = ["recipe", "setup.rx", "-", "demo", "command", "--help"]
    assert bootstrap._run_runtime_recipe(args) == 0
    assert calls == [args]


def test_bootstrap_delegates_upgrade_execution_to_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    class FakeRuntime:
        def __init__(self, **kwargs) -> None:
            pass

        def execute(self, tokens, *, interactive=False, **kwargs):
            calls.append((list(tokens), interactive))
            return {"status": "skipped", "name": "demo"}

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)
    monkeypatch.setattr(bootstrap, "_render_upgrade_result", lambda result, detail: None)

    assert bootstrap._run_runtime_lifecycle(["-i", "upgrade", "demo"]) == 0
    assert calls == [(["upgrade", "demo"], True)]


def test_bootstrap_renders_completed_upgrade_before_later_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeRuntime:
        def __init__(self, *, on_progress=None, **kwargs) -> None:
            self.on_progress = on_progress

        def execute(self, tokens, **kwargs):
            assert self.on_progress is not None
            self.on_progress({"status": "upgraded", "name": "first"})
            raise UpgradeError("second failed")

    monkeypatch.setattr("gway.runtime.GwayRuntime", FakeRuntime)

    assert bootstrap._run_runtime_lifecycle(["upgrade", "first", "second"]) == 2
    captured = capsys.readouterr()
    assert "upgraded first" in captured.out
    assert "second failed" in captured.err


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
