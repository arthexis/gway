from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import DispatchError, Dispatcher
from gway.project import Project
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "routing-project"
    root.mkdir()
    (root / "routing_commands.py").write_text(
        """def values() -> list[str]:
    return ["A", "B", "C", "D"]


def grammar_values() -> list[str]:
    return ["[cwd]", "--help", "--", "--unknown"]


def number() -> int:
    return 42


def mapping() -> dict[str, str]:
    return {"extra": "CTX", "project": "shadow", "command": "shadow-command"}


def collect(*values: str) -> list[str]:
    return list(values)


def integer(value: int) -> int:
    return value


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("routing_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="route",
            path=root,
            adapter_type="python",
            adapter_config={"module": "routing_commands"},
        )
    )
    return Dispatcher(registry)


def _run(dispatcher: Dispatcher, args: list[str], capsys) -> str:
    assert main(args, dispatcher=dispatcher) == 0
    return capsys.readouterr().out


def test_numeric_selectors_reorder_transfer(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "values", "-", "route", "collect", "[2]", "[1]"],
        capsys,
    )
    assert output == "- B\n- A\n"


def test_wildcard_contributes_unselected_values_in_original_order(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "values", "-", "route", "collect", "[3]", "[*]", "[1]"],
        capsys,
    )
    assert output == "- C\n- B\n- D\n- A\n"


def test_duplicate_numeric_selectors_are_allowed(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "values", "-", "route", "collect", "[2]", "[2]"],
        capsys,
    )
    assert output == "- B\n- B\n"


def test_explicit_selector_disables_implicit_transfer(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "values", "-", "route", "collect", "[2]", "tail"],
        capsys,
    )
    assert output == "- B\n- tail\n"


def test_ordinary_sigil_keeps_implicit_transfer(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        [
            "route",
            "mapping",
            "-",
            "route",
            "values",
            "-",
            "route",
            "collect",
            "[extra]",
        ],
        capsys,
    )
    assert output == "- A\n- B\n- C\n- D\n- CTX\n"


def test_multiple_wildcards_are_rejected(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    with pytest.raises(DispatchError, match="at most one"):
        main(
            ["route", "values", "-", "route", "collect", "[*]", "[*]"],
            dispatcher=dispatcher,
        )


def test_out_of_range_selector_is_rejected(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    with pytest.raises(DispatchError, match=r"\[5\].*out of range"):
        main(
            ["route", "values", "-", "route", "collect", "[5]"],
            dispatcher=dispatcher,
        )


def test_mapping_result_has_no_numbered_transfer_values(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    with pytest.raises(DispatchError, match=r"\[1\].*out of range"):
        main(
            ["route", "mapping", "-", "route", "collect", "[1]"],
            dispatcher=dispatcher,
        )


def test_transferred_cli_and_sigil_like_strings_remain_literal(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "grammar-values", "-", "route", "collect"],
        capsys,
    )
    assert output == "- [cwd]\n- --help\n- --\n- --unknown\n"


def test_typed_scalar_transfer_still_reaches_typed_consumer(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "number", "-", "route", "integer"],
        capsys,
    )
    assert output == "42\n"


def test_reserved_mapping_keys_do_not_break_later_dispatch(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "mapping", "-", "route", "echo", "[extra]"],
        capsys,
    )
    assert output == "CTX\n"


def test_reserved_project_context_remains_framework_owned(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)
    output = _run(
        dispatcher,
        ["route", "mapping", "-", "route", "echo", "[project.name]"],
        capsys,
    )
    assert output == "route\n"
