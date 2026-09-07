from __future__ import annotations

import json
import sys
from pathlib import Path

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
        ("peer", "add"),
        ("peer", "echo-values"),
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


def test_python_command_help_uses_docstring(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fixture", "peer", "add", "--help"], dispatcher=dispatcher) == 0
    output = capsys.readouterr().out

    assert "Add a fixture peer." in output
    assert "--enabled | --no-enabled" in output
    assert "--mode {fast,safe}" in output


def test_project_command_json_output(tmp_path: Path, capsys) -> None:
    dispatcher = make_dispatcher(tmp_path)

    assert main(["fixture", "status", "--json"], dispatcher=dispatcher) == 0

    assert json.loads(capsys.readouterr().out) == {"status": "ok"}
