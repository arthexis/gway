from __future__ import annotations

import sys
from pathlib import Path

from gway.chain import run_statement
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def test_statement_can_read_existing_named_context(tmp_path: Path) -> None:
    root = tmp_path / "context-project"
    root.mkdir()
    (root / "context_commands.py").write_text(
        """def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("context_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "context_commands"},
        )
    )

    result = run_statement(
        Dispatcher(registry),
        ["demo", "echo", "[name]"],
        context={"name": "mapped"},
    )

    assert result == "mapped"
