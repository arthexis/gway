from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.chain import run_chain
from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.solve import solve_values


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "chain-project"
    root.mkdir()
    (root / "chain_commands.py").write_text(
        """MARKS = []


def scalar() -> str:
    return "alpha"


def sequence() -> list[str]:
    return ["one", "two"]


def mapping() -> dict[str, str]:
    return {"name": "mapped", "status": "ready"}


def nothing() -> None:
    return None


def echo(value: str) -> str:
    return value


def collect(*values: str) -> list[str]:
    return list(values)


def fail() -> None:
    raise RuntimeError("chain failure")


def mark() -> str:
    MARKS.append("ran")
    return "ran"
""",
        encoding="utf-8",
    )
    sys.modules.pop("chain_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "chain_commands"},
        )
    )
    return Dispatcher(registry)


def test_scalar_result_becomes_first_positional(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert main(["demo", "scalar", "-", "demo", "echo"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "alpha\n"


def test_sequence_result_spreads_into_positionals(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert main(["demo", "sequence", "-", "demo", "collect"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "- one\n- two\n"


def test_mapping_result_updates_chain_context_without_positional_transfer(
    tmp_path: Path,
    capsys,
) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert (
        main(
            ["demo", "mapping", "-", "demo", "echo", "[name]"],
            dispatcher=dispatcher,
        )
        == 0
    )
    assert capsys.readouterr().out == "mapped\n"


def test_none_result_transfers_no_positionals(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert (
        main(
            ["demo", "nothing", "-", "demo", "collect", "tail"],
            dispatcher=dispatcher,
        )
        == 0
    )
    assert capsys.readouterr().out == "- tail\n"


def test_solve_stage_can_produce_for_command_stage(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert main(["%", "hello", "-", "demo", "echo"], dispatcher=dispatcher) == 0
    assert capsys.readouterr().out == "hello\n"


def test_mapping_context_is_visible_to_later_solve_stage(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert (
        main(
            ["demo", "mapping", "-", "%", "[name]"],
            dispatcher=dispatcher,
        )
        == 0
    )
    assert capsys.readouterr().out == "mapped\n"


def test_result_sigil_exposes_latest_full_mapping(tmp_path: Path, capsys) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert (
        main(
            ["demo", "mapping", "-", "%", "[result]"],
            dispatcher=dispatcher,
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "name: mapped" in output
    assert "status: ready" in output


def test_failure_aborts_later_stages(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    with pytest.raises(RuntimeError, match="chain failure"):
        main(["demo", "fail", "-", "demo", "mark"], dispatcher=dispatcher)

    module = sys.modules["chain_commands"]
    assert module.MARKS == []


def test_chain_context_is_restored_after_execution(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert run_chain(
        dispatcher,
        ["demo", "mapping", "-", "%", "[name]"],
    ) == "mapped"
    assert solve_values(["[name]"], paths=dispatcher.registry.paths) == "[name]"


def test_literal_dash_after_double_dash_is_not_a_chain(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)

    assert run_chain(
        dispatcher,
        ["demo", "collect", "--", "-", "-", "%", "done"],
    ) == "done"
