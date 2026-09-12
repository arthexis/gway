from __future__ import annotations

import sys
from pathlib import Path

from gway.chain import run_statement
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.solve import solve_values


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "statement-project"
    root.mkdir()
    (root / "statement_commands.py").write_text(
        """def scalar() -> str:
    return "alpha"


def mapping() -> dict[str, str]:
    return {"name": "mapped", "status": "ready"}


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("statement_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "statement_commands"},
        )
    )
    return Dispatcher(registry)


def test_statement_preserves_existing_chain_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_statement(
        dispatcher,
        ["demo", "scalar", "-", "demo", "echo"],
    )

    assert result == "alpha"


def test_statement_can_publish_into_caller_owned_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    result = run_statement(dispatcher, ["demo", "mapping"], context=context)

    assert result == {"name": "mapped", "status": "ready"}
    assert context == {
        "name": "mapped",
        "status": "ready",
        "result": {"name": "mapped", "status": "ready"},
    }


def test_statement_restores_context_after_execution(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    context: dict[str, object] = {}

    run_statement(dispatcher, ["demo", "mapping"], context=context)

    assert solve_values(["[name]"], paths=dispatcher.registry.paths) == "[name]"
