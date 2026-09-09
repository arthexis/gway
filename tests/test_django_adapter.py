from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gway.adapters.django import DjangoAdapter, _parameter_from_action
from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher, _provided_positional_count
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
    assert "echo" in output


def test_django_check_runs_through_native_management_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert main(["django-fixture", "check"], dispatcher=dispatcher) == 0
    assert "System check identified no issues" in capsys.readouterr().out


def test_django_check_json_stdout_is_one_json_value(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert main(["--json", "django-fixture", "check"], dispatcher=dispatcher) == 0
    output = json.loads(capsys.readouterr().out)
    assert "System check identified no issues" in output


def test_django_migrate_preserves_native_plan_option(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert main(["django-fixture", "migrate", "--plan"], dispatcher=dispatcher) == 0
    assert "Planned operations" in capsys.readouterr().out


def test_django_parameter_metadata_preserves_declared_option_spellings() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_argument("-t", "--target", dest="device", required=True)
    parameter = _parameter_from_action(action)
    assert parameter is not None
    assert parameter.name == "device"
    assert parameter.options == ("-t", "--target")
    assert parameter.consumes_value is True
    assert parameter.option_arity is None


def test_django_parameter_metadata_marks_zero_arity_options() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_argument("--traceback", action="store_true")
    parameter = _parameter_from_action(action)
    assert parameter is not None
    assert parameter.consumes_value is False
    assert parameter.option_arity == 0


def test_django_parameter_metadata_preserves_multi_value_arity() -> None:
    parser = argparse.ArgumentParser()
    pair_action = parser.add_argument("--pair", nargs=2)
    positional_action = parser.add_argument("value")
    pair = _parameter_from_action(pair_action)
    positional = _parameter_from_action(positional_action)
    assert pair is not None
    assert positional is not None
    assert pair.option_arity == 2
    command = __import__("gway.command", fromlist=["Command"]).Command(
        ("example",), parameters=(pair, positional)
    )
    assert _provided_positional_count(command, ["--pair", "a", "b"]) == 0


def test_django_interactive_preserves_positional_after_zero_arity_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)

    def unexpected_input() -> str:
        raise AssertionError("interactive mode should not prompt for an existing positional")

    monkeypatch.setattr("builtins.input", unexpected_input)
    args = ["django-fixture", "echo", "-i", "--traceback", "hello"]
    assert main(args, dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "hello\n"


def test_django_sigil_context_reaches_real_management_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert main(["django-fixture", "echo", "[THING.name]"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "demo\n"


def test_django_sigil_provider_receives_project_and_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    assert main(["django-fixture", "echo", "[THING.project]"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "django-fixture\n"
    assert main(["django-fixture", "echo", "[THING.command]"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "echo\n"


def test_django_safe_namespace_blocks_tool_escape(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    token = "[THING.name.upper]"
    assert main(["django-fixture", "echo", token], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == f"{token}\n"


def test_django_helper_module_without_command_is_ignored() -> None:
    class Base:
        class BaseCommand:
            pass

    class Management:
        @staticmethod
        def load_command_class(source, name):
            raise AttributeError(
                f"module '{source}.management.commands.{name}' has no attribute 'Command'",
                name="Command",
            )

    assert DjangoAdapter._load_command("utils", "apps.users", Management, Base) is None


def test_runner_prepares_django_project_environment(monkeypatch, tmp_path: Path) -> None:
    project = Project(
        name="django-fixture",
        path=FIXTURE_ROOT,
        adapter_type="django",
        adapter_config={"manage": "manage.py", "settings": "gway_django_fixture.settings"},
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
    assert calls[1][-1] == str(FIXTURE_ROOT)
    assert "-e" not in calls[1]
