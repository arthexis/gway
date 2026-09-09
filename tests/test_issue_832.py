from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gway.cli as cli
from gway.adapters.python import PythonAdapter
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def test_upgrade_all_includes_self_unless_explicitly_disabled(monkeypatch, tmp_path, capsys) -> None:
    calls: list[str] = []
    project = Project(
        name="fixture",
        path=tmp_path / "fixture",
        adapter_type="python",
        adapter_config={"module": "fixture.gway"},
        repository="arthexis/gway-fixture",
        revision="abc123",
    )

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def upgrade_self(self) -> None:
            calls.append("self")

        def all_project_results(self, *, force: bool = False, reload: bool = False):
            calls.append("all")
            return [SimpleNamespace(project=project, changed=True)]

    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["upgrade", "--all"], dispatcher=dispatcher) == 0
    assert calls == ["self", "all"]
    calls.clear()
    capsys.readouterr()

    assert cli.main(["upgrade", "--all", "--no-self"], dispatcher=dispatcher) == 0
    assert calls == ["all"]


def test_upgrade_self_only_still_skips_managed_projects(monkeypatch, capsys) -> None:
    calls: list[str] = []

    class FakeUpgrader:
        def __init__(self, registry) -> None:
            pass

        def upgrade_self(self) -> None:
            calls.append("self")

        def all_project_results(self, *, force: bool = False, reload: bool = False):
            calls.append("all")
            return []

    monkeypatch.setattr(cli, "Upgrader", FakeUpgrader)
    dispatcher = SimpleNamespace(registry=object())

    assert cli.main(["upgrade", "--self"], dispatcher=dispatcher) == 0
    capsys.readouterr()
    assert calls == ["self"]


def _managed_project(tmp_path: Path) -> Project:
    root = tmp_path / "project"
    package = root / "src" / "fixture" / "gway"
    package.mkdir(parents=True)
    (root / "gway.toml").write_text(
        """[project]
name = "fixture"

[adapter]
type = "python"
module = "fixture.gway"
""",
        encoding="utf-8",
    )
    (root / "src" / "fixture" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text(
        """def options(*, retries: int = 3, mode: str = \"safe\", enabled: bool = True):
    return {\"retries\": retries, \"mode\": mode, \"enabled\": enabled}


def required(*, value: str):
    return value
""",
        encoding="utf-8",
    )
    return Project.from_path(root)


def _dispatcher(tmp_path: Path) -> Dispatcher:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(_managed_project(tmp_path))
    return Dispatcher(registry)


def test_value_flags_accept_no_form_and_pass_explicit_none(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = dispatcher.run(
        "fixture",
        ["options", "--no-retries", "--no-mode", "--no-enabled"],
    )

    assert result == {"retries": None, "mode": None, "enabled": False}


def test_required_keyword_flag_accepts_no_form_as_explicit_none(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run("fixture", ["required", "--no-value"]) is None


def test_value_flag_help_lists_no_form(tmp_path: Path, capsys) -> None:
    adapter = PythonAdapter(_managed_project(tmp_path))

    assert adapter.run(("options",), ["--help"]) is None
    output = capsys.readouterr().out
    assert "--retries" in output
    assert "--no-retries" in output
    assert "--mode" in output
    assert "--no-mode" in output
