from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

import gway.chain as chain_module
from gway.chain import run_statement
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime
from gway.runtime_reload import capture_pending_chains
from gway.stage import Stage


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "chunk734-project"
    root.mkdir()
    (root / "chunk734_commands.py").write_text(
        """def collect(*values: str) -> list[str]:
    return list(values)
""",
        encoding="utf-8",
    )
    sys.modules.pop("chunk734_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "chunk734_commands"},
        )
    )
    return Dispatcher(registry)


def test_restored_selector_stage_routes_saved_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    runtime = GwayRuntime(dispatcher)
    tokens = ("demo", "skipped", "-", "demo", "collect", "[2]", "[1]")

    with runtime.frame_scope("statement", tokens=tokens):
        result = run_statement(
            dispatcher,
            tokens,
            runtime=runtime,
            start_stage_index=1,
            initial_result=["one", "two"],
            has_initial_result=True,
        )

    assert result == ["two", "one"]


def test_restored_solve_stage_escapes_transferred_sigils(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_solve(values, *, interactive=False, prompt=None, paths=None):
        observed["values"] = tuple(values)
        return "resolved"

    monkeypatch.setattr(chain_module, "solve_values", fake_solve)
    runtime = GwayRuntime()
    tokens = ("demo", "skipped", "-", "%", "tail")

    with runtime.frame_scope("statement", tokens=tokens):
        result = run_statement(
            runtime.dispatcher,
            tokens,
            runtime=runtime,
            start_stage_index=1,
            initial_result=["[name]", "plain"],
            has_initial_result=True,
        )

    assert result == "resolved"
    assert observed["values"] == ("[[name]]", "plain", "tail")


def test_three_level_pending_chain_capture_preserves_outer_to_inner_order() -> None:
    runtime = GwayRuntime()

    with runtime.frame_scope("recipe", recipe_path="outer.rx") as outer:
        with runtime.frame_scope("statement", recipe_path="outer.rx", recipe_line=1):
            with runtime.frames.chain_continuation_scope(
                statement_tokens=("recipe", "middle.rx", "-", "demo", "after-outer"),
                recipe_path="outer.rx",
                recipe_line=1,
            ) as outer_chain:
                assert outer_chain is not None
                outer_chain.active_stage_index = 1
                with runtime.frame_scope("recipe", recipe_path="middle.rx") as middle:
                    with runtime.frame_scope(
                        "statement", recipe_path="middle.rx", recipe_line=2
                    ):
                        with runtime.frames.chain_continuation_scope(
                            statement_tokens=(
                                "recipe",
                                "inner.rx",
                                "-",
                                "demo",
                                "after-middle",
                            ),
                            recipe_path="middle.rx",
                            recipe_line=2,
                        ) as middle_chain:
                            assert middle_chain is not None
                            middle_chain.active_stage_index = 1
                            with runtime.frame_scope(
                                "recipe", recipe_path="inner.rx"
                            ) as inner:
                                with runtime.frame_scope(
                                    "statement",
                                    recipe_path="inner.rx",
                                    recipe_line=3,
                                ):
                                    with runtime.frames.chain_continuation_scope(
                                        statement_tokens=(
                                            "reload",
                                            "-",
                                            "demo",
                                            "after-inner",
                                        ),
                                        recipe_path="inner.rx",
                                        recipe_line=3,
                                    ) as inner_chain:
                                        assert inner_chain is not None
                                        inner_chain.active_stage_index = 1
                                        pending = capture_pending_chains(runtime)

    assert [chain.frame_id for chain in pending] == [outer.id, middle.id, inner.id]
    assert [chain.recipe_path for chain in pending] == [
        "outer.rx",
        "middle.rx",
        "inner.rx",
    ]
    assert [chain.remaining_stages[0].raw_tokens for chain in pending] == [
        ("demo", "after-outer"),
        ("demo", "after-middle"),
        ("demo", "after-inner"),
    ]
    assert runtime.frames.active_chains == ()


class _FailingRuntime(GwayRuntime):
    def execute_stage(
        self,
        stage: Stage,
        transfer: Sequence[object],
        *,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
        previous_result: object = None,
        has_previous_result: bool = False,
    ) -> object:
        raise RuntimeError("resumed stage failed")


def test_resumed_stage_failure_cleans_active_chain_state() -> None:
    runtime = _FailingRuntime()
    tokens = ("demo", "skipped", "-", "demo", "fails")

    with runtime.frame_scope("recipe", recipe_path="failure.rx"):
        with runtime.frame_scope(
            "statement",
            tokens=tokens,
            recipe_path="failure.rx",
            recipe_line=4,
        ):
            with pytest.raises(RuntimeError, match="resumed stage failed"):
                run_statement(
                    runtime.dispatcher,
                    tokens,
                    runtime=runtime,
                    start_stage_index=1,
                    initial_result="saved",
                    has_initial_result=True,
                )

    assert runtime.frames.active_chains == ()
