from __future__ import annotations

import json
import sys
from pathlib import Path

import gway.cli as cli
from gway.adapters import AdapterRegistry
from gway.adapters.python import PythonAdapter
from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def make_python_project(tmp_path: Path) -> Project:
    root = tmp_path / "fixture-project"
    package = root / "src" / "fixture_project" / "gway"
    package.mkdir(parents=True)

    (root / "gway.toml").write_text(
        """[project]
name = "fixture"
aliases = ["fx"]

[adapter]
type = "python"
module = "fixture_project.gway"
""",
        encoding="utf-8",
    )
    (root / "src" / "fixture_project" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text(
        """def status() -> dict[str, str]:
    \"\"\"Show fixture status.\"\"\"
    return {\"status\": \"ok\"}


def denied() -> None:
    \"\"\"Raise a real OS permission failure.\"\"\"
    raise PermissionError(13, \"Permission denied\", \"/fixture/protected\")


def _private() -> str:
    return \"hidden\"
""",
        encoding="utf-8",
    )
    (package / "peer.py").write_text(
        """from pathlib import Path
from typing import Literal


def add(
    name: str,
    address: str,
    *,
    enabled: bool = True,
    retries: int = 1,
    mode: Literal[\"fast\", \"safe\"] = \"safe\",
    target: Path | None = None,
) -> dict[str, object]:
    \"\"\"Add a fixture peer.\"\"\"
    return {
        \"name\": name,
        \"address\": address,
        \"enabled\": enabled,
        \"retries\": retries,
        \"mode\": mode,
        \"target\": str(target) if target else None,
    }


def echo_values(prefix: str, *values: int) -> list[object]:
    \"\"\"Echo typed variadic values.\"\"\"
    return [prefix, *values]


def echo_flags(*values: bool) -> list[bool]:
    return list(values)


def positional_limit(limit: int = 10, /) -> int:
    return limit
""",
        encoding="utf-8",
    )
    (package / "_internal.py").write_text(
        "def hidden() -> str:\n    return 'hidden'\n",
        encoding="utf-8",
    )

    for name in tuple(sys.modules):
        if name == "fixture_project" or name.startswith("fixture_project."):
            del sys.modules[name]

    return Project.from_path(root)


def make_single_module_project(tmp_path: Path) -> Project:
    root = tmp_path / "single-module-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "single"

[adapter]
type = "python"
module = "commands"
""",
        encoding="utf-8",
    )
    (root / "commands.py").write_text(
        """def lazy_value() -> str:
    import sibling

    return sibling.VALUE
""",
        encoding="utf-8",
    )
    (root / "sibling.py").write_text("VALUE = 'loaded'\n", encoding="utf-8")

    for name in ("commands", "sibling"):
        sys.modules.pop(name, None)
    return Project.from_path(root)


def make_dispatcher(tmp_path: Path) -> Dispatcher:
    project = make_python_project(tmp_path)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(project)
    return Dispatcher(registry)


def test_registry_provides_python_adapter_by_default(tmp_path: Path) -> None:
    project = make_python_project(tmp_path)

    adapter = AdapterRegistry().create(project)

    assert isinstance(adapter, PythonAdapter)


def test_python_adapter_discovers_public_nested_functions(tmp_path: Path) -> None:
    adapter = PythonAdapter(make_python_project(tmp_path))

    commands = {command.path: command for command in adapter.commands()}

    assert set(commands) == {
        ("denied",),
        ("peer", "add"),
        ("peer", "echo-flags"),
        ("peer", "echo-values"),
        ("peer", "positional-limit"),
        ("status",),
    }
    assert commands[("peer", "add")].summary == "Add a fixture peer."
    assert [parameter.name for parameter in commands[("peer", "add")].parameters] == [
        "name",
        "address",
        "enabled",
        "retries",
        "mode",
        "target",
    ]


def test_python_adapter_converts_typed_arguments(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)
    target = tmp_path / "peer.conf"

    result = dispatcher.run(
        "fixture",
        [
            "peer",
            "add",
            "gway-004",
            "10.44.0.4",
            "--no-enabled",
            "--retries",
            "3",
            "--mode",
            "fast",
            "--target",
            str(target),
        ],
    )

    assert result == {
        "name": "gway-004",
        "address": "10.44.0.4",
        "enabled": False,
        "retries": 3,
        "mode": "fast",
        "target": str(target),
    }


def test_python_adapter_supports_typed_varargs(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fx", ["peer", "echo-values", "numbers", "1", "2", "3"])

    assert result == ["numbers", 1, 2, 3]


def test_python_adapter_decodes_escaped_argument_values_after_command_resolution(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fixture", ["peer", "echo-values", "[-]"])

    assert result == ["-"]


def test_python_adapter_parses_boolean_varargs(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    result = dispatcher.run("fixture", ["peer", "echo-flags", "true", "false", "0", "on"])

    assert result == [True, False, False, True]


def test_python_adapter_passes_defaulted_positional_only_arguments(tmp_path: Path) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert dispatcher.run("fixture", ["peer", "positional-limit"]) == 10
    assert dispatcher.run("fixture", ["peer", "positional-limit", "--limit", "7"]) == 7


def test_python_adapter_keeps_project_path_active_during_execution(tmp_path: Path) -> None:
    project = make_single_module_project(tmp_path)
    adapter = PythonAdapter(project)

    assert adapter.run(("lazy-value",), []) == "loaded"


def test_python_command_help_uses_docstring(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fixture", "peer", "add", "--help"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out

    assert "Add a fixture peer." in output
    assert "--enabled | --no-enabled" in output
    assert "--mode {fast,safe}" in output


def test_project_command_json_output_uses_global_flag(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["--json", "fixture", "status"], dispatcher=dispatcher) == 0

    assert json.loads(capsys.readouterr().out) == {"status": "ok"}


def test_managed_permission_failure_suggests_original_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dispatcher = make_dispatcher(tmp_path)
    monkeypatch.setattr(cli, "_can_suggest_sudo", lambda: True)

    assert main(["fixture", "denied"], dispatcher=dispatcher) == 2
    error = capsys.readouterr().err
    assert "Permission denied" in error
    assert "sudo gway fixture denied" in error
