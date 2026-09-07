from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.runner import Runner

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "django_project"


def make_dispatcher(tmp_path: Path) -> Dispatcher:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register_path(FIXTURE_ROOT)
    return Dispatcher(registry)


def test_django_project_help_uses_discovered_management_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["django-fixture", "--help"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out

    assert "usage: gway django-fixture <command> [arguments]" in output
    assert "check" in output
    assert "migrate" in output


def test_django_check_runs_through_native_management_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["django-fixture", "check"], dispatcher=dispatcher) == 0

    assert "System check identified no issues" in capsys.readouterr().out


def test_django_migrate_preserves_native_plan_option(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["django-fixture", "migrate", "--plan"], dispatcher=dispatcher) == 0

    assert "Planned operations" in capsys.readouterr().out


def test_runner_prepares_django_project_environment(monkeypatch, tmp_path: Path) -> None:
    project = Project(
        name="django-fixture",
        path=FIXTURE_ROOT,
        adapter_type="django",
        adapter_config={
            "manage": "manage.py",
            "settings": "gway_django_fixture.settings",
        },
    )
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append([str(value) for value in args])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("gway.runner.subprocess.run", fake_run)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")

    environment = Runner(paths).prepare(project)

    assert environment == paths.environments_dir / "django-fixture"
    assert calls[0][1:3] == ["-m", "venv"]
    assert calls[1][-2:] == ["-e", str(FIXTURE_ROOT)]
