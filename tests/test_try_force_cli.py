from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.cli import _render_upgrade_record, _upgrade_status, build_parser
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.errors import DispatchError
from gway.project import Project
from gway.registry import Registry
from gway.repository import WorkingTreeEntry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    return Dispatcher(registry)


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "fixture"
    root.mkdir(exist_ok=True)
    return Project(
        name="fixture",
        path=root,
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        repository="arthexis/gway-fixture",
        revision="new-revision",
    )


def _result(project: Project, *, forced: bool = False):
    return SimpleNamespace(
        project=project,
        changed=True,
        force_used=forced,
        force_error_type="RepositoryError" if forced else None,
        force_error="managed checkout has local changes" if forced else None,
        dirty_files=(WorkingTreeEntry(status=" M", path="src/example.py"),) if forced else (),
    )


def test_cli_parser_exposes_try_force() -> None:
    namespace = build_parser().parse_args(["upgrade", "fixture", "--try-force"])

    assert namespace.try_force is True
    assert namespace.force is False


def test_cli_parser_rejects_force_with_try_force() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["upgrade", "fixture", "--force", "--try-force"])


def test_runtime_forwards_try_force_to_single_project(tmp_path: Path, monkeypatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    project = _project(tmp_path)
    calls: list[tuple[str, bool, bool]] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            assert registry is dispatcher.registry

        def project_result(self, name, *, force=False, try_force=False, reload=False, arguments=()):
            calls.append((name, force, try_force))
            return _result(project, forced=True)

    monkeypatch.setattr("gway.runtime.Upgrader", FakeUpgrader)

    result = GwayRuntime(dispatcher).execute(["upgrade", "fixture", "--try-force"])

    assert calls == [("fixture", False, True)]
    assert result["force_used"] is True
    assert result["force_error_type"] == "RepositoryError"
    assert result["force_error"] == "managed checkout has local changes"
    assert result["dirty_files"] == [{"status": " M", "path": "src/example.py"}]


def test_runtime_forwards_try_force_to_all_projects(tmp_path: Path, monkeypatch) -> None:
    dispatcher = _dispatcher(tmp_path)
    project = _project(tmp_path)
    calls: list[tuple[bool, bool]] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            assert registry is dispatcher.registry

        def upgrade_self(self) -> None:
            pass

        def all_project_results(self, *, force=False, try_force=False, reload=False):
            calls.append((force, try_force))
            return [_result(project)]

    monkeypatch.setattr("gway.runtime.Upgrader", FakeUpgrader)

    result = GwayRuntime(dispatcher).execute(["upgrade", "--all", "--try-force", "--no-self"])

    assert calls == [(False, True)]
    assert result[0]["force_used"] is False


def test_runtime_rejects_force_with_try_force(tmp_path: Path) -> None:
    with pytest.raises(DispatchError, match="not allowed with argument"):
        GwayRuntime(_dispatcher(tmp_path)).execute(
            ["upgrade", "fixture", "--force", "--try-force"]
        )


def test_upgrade_status_exposes_force_metadata(tmp_path: Path) -> None:
    record = _upgrade_status("upgraded", _result(_project(tmp_path), forced=True))

    assert record["force_used"] is True
    assert record["force_error_type"] == "RepositoryError"
    assert record["dirty_files"] == [{"status": " M", "path": "src/example.py"}]


def test_compact_upgrade_renderer_ignores_force_metadata(tmp_path: Path, capsys) -> None:
    record = _upgrade_status("upgraded", _result(_project(tmp_path), forced=True))

    _render_upgrade_record(record, detail=False)

    output = capsys.readouterr().out
    assert output.startswith("upgraded fixture ")
    assert "force_used" not in output
    assert "src/example.py" not in output
