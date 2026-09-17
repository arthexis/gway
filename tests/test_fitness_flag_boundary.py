from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.recipe import run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "fitness-flags"
    root.mkdir()
    (root / "fitness_flags.py").write_text(
        '''CALLS = []


def operate(*, role: str = "operation-default", service: bool = False) -> str:
    CALLS.append(("operate", role, service))
    return "ready"


def good(*, role: str = "fitness-default", service: bool = False) -> bool:
    CALLS.append(("good", role, service))
    return role == "fitness-default" and service is False


def calls():
    return list(CALLS)
''',
        encoding="utf-8",
    )
    sys.modules.pop("fitness_flags", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "fitness_flags"},
        )
    )
    return Dispatcher(registry)


def test_continuation_flags_belong_only_to_operation(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "flags.rx"
    path.write_text(
        "demo operate --> demo good:\n"
        "    --role Watchtower\n"
        "    --service\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "ready"
    assert dispatcher.invoke("demo", ("calls",)) == [
        ("operate", "Watchtower", True),
        ("good", "fitness-default", False),
    ]


def test_fitness_command_standalone_keeps_its_own_flags(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert dispatcher.run(
        "demo",
        ["good", "--role", "manual", "--service"],
    ) is False
    assert dispatcher.invoke("demo", ("calls",)) == [
        ("good", "manual", True),
    ]
