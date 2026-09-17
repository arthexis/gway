from __future__ import annotations

import sys
from pathlib import Path

from gway.chain import run_chain
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "optional-positional-project"
    root.mkdir()
    (root / "commands.py").write_text(
        """def produce() -> str:
    return \"alpha\"


def optional(value: str = \"default\") -> str:
    return value


def keyword_only(*, value: str = \"default\") -> str:
    return value


def no_args() -> str:
    return \"ready\"


def variadic(*values: str) -> list[str]:
    return list(values)
""",
        encoding="utf-8",
    )
    sys.modules.pop("commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="optional-positional",
            path=root,
            adapter_type="python",
            adapter_config={"module": "commands"},
        )
    )
    return Dispatcher(registry)


def test_optional_positional_or_keyword_accepts_chain_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["optional-positional", "produce", "-", "optional-positional", "optional"],
    )

    assert result == "alpha"


def test_callable_signature_capability_is_distinct_from_cli_shape(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    optional = dispatcher.describe("optional-positional", ("optional",))
    keyword_only = dispatcher.describe("optional-positional", ("keyword-only",))
    no_args = dispatcher.describe("optional-positional", ("no-args",))
    variadic = dispatcher.describe("optional-positional", ("variadic",))

    optional_parameter = optional.parameters[0]
    assert optional_parameter.positional is False
    assert optional_parameter.accepts_positional is True
    assert optional.accepts_positional_transfer is True
    assert keyword_only.accepts_positional_transfer is False
    assert no_args.accepts_positional_transfer is False
    assert variadic.accepts_positional_transfer is True


def test_keyword_only_target_still_omits_implicit_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    result = run_chain(
        dispatcher,
        ["optional-positional", "produce", "-", "optional-positional", "keyword-only"],
    )

    assert result == "default"
