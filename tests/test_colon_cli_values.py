from __future__ import annotations

import json
import sys
from pathlib import Path

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "colon-project"
    root.mkdir()
    (root / "gway.toml").write_text(
        """[project]
name = "colon"

[adapter]
type = "python"
module = "colon_commands"
""",
        encoding="utf-8",
    )
    (root / "colon_commands.py").write_text(
        """def token(
    *token_id: str,
    name: str | None = None,
    scope: str = "logs:read",
    ttl: int = 7776000,
    list: bool = False,
    revoke: bool = False,
):
    return {
        "token_id": token_id,
        "name": name,
        "scope": scope,
        "ttl": ttl,
        "list": list,
        "revoke": revoke,
    }


def echo(*values: str):
    return values
""",
        encoding="utf-8",
    )
    sys.modules.pop("colon_commands", None)

    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(Project.from_path(root))
    return Dispatcher(registry)


def test_cli_keyword_option_keeps_colon_value_out_of_varargs(
    tmp_path: Path,
    capsys,
) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert (
        main(
            ["--json", "colon", "token", "--scope", "logs:read"],
            dispatcher=dispatcher,
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)

    assert result["token_id"] == []
    assert result["scope"] == "logs:read"


def test_colon_bearing_cli_values_are_opaque_data(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    values = [
        "logs:read",
        "https://logs.arthexis.com/api/logs/run/events",
        "12:30",
        "foo:bar:baz",
    ]

    assert dispatcher.run("colon", ["echo", *values]) == tuple(values)
