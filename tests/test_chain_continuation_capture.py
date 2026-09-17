from __future__ import annotations

from collections.abc import Callable, Sequence

from gway.checkpoint.chain import PendingChainCheckpoint
from gway.provenance import ExecutionFrameStack, ValueProvenance
from gway.runtime import GwayRuntime
from gway.runtime_reload import capture_pending_chains
from gway.stage import Stage


class _CaptureRuntime(GwayRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.snapshots: list[tuple[PendingChainCheckpoint, ...]] = []
        self.calls = 0

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
        self.calls += 1
        if self.calls == 2:
            self.snapshots.append(capture_pending_chains(self))
        return ("alpha", "beta", "omega")[self.calls - 1]


def test_run_statement_exposes_active_stage_and_previous_result() -> None:
    runtime = _CaptureRuntime()

    with runtime.frame_scope("recipe", recipe_path="demo.rx"):
        result = runtime.execute(
            ["demo", "one", "-", "demo", "two", "-", "demo", "three"],
            recipe_path="demo.rx",
            recipe_line=7,
        )

    assert result == "omega"
    assert len(runtime.snapshots) == 1
    pending = runtime.snapshots[0]
    assert len(pending) == 1
    chain = pending[0]
    assert chain.recipe_path == "demo.rx"
    assert chain.recipe_line == 7
    assert chain.active_stage_index == 2
    assert chain.has_previous_result is True
    assert chain.previous_result == "alpha"
    assert [stage.raw_tokens for stage in chain.remaining_stages] == [("demo", "three")]
    assert runtime.frames.active_chains == ()


def test_chain_capture_preserves_previous_result_provenance() -> None:
    frames = ExecutionFrameStack()
    provenance = ValueProvenance(
        frame_id="producer",
        frame_kind="operation",
        operation="demo.one",
        tokens=("demo", "one"),
        recipe_path="outer.rx",
        recipe_line=3,
    )

    with frames.scope("recipe", recipe_path="outer.rx") as recipe_frame:
        with frames.scope(
            "statement", recipe_path="outer.rx", recipe_line=3
        ):
            with frames.chain_continuation_scope(
                statement_tokens=("demo", "one", "-", "demo", "two"),
                recipe_path="outer.rx",
                recipe_line=3,
            ) as state:
                assert state is not None
                state.active_stage_index = 1
                state.has_previous_result = True
                state.previous_result = {"value": "kept"}
                state.previous_result_provenance = provenance
                assert state.frame_id == recipe_frame.id
                assert frames.active_chains == (state,)

    assert frames.active_chains == ()


def test_nested_chain_capture_is_outer_to_inner() -> None:
    frames = ExecutionFrameStack()

    with frames.scope("recipe", recipe_path="outer.rx") as outer:
        with frames.scope("statement", recipe_path="outer.rx", recipe_line=2):
            with frames.chain_continuation_scope(
                statement_tokens=("recipe", "inner.rx", "-", "demo", "after"),
                recipe_path="outer.rx",
                recipe_line=2,
            ) as outer_chain:
                with frames.scope("recipe", recipe_path="inner.rx") as inner:
                    with frames.scope(
                        "statement", recipe_path="inner.rx", recipe_line=4
                    ):
                        with frames.chain_continuation_scope(
                            statement_tokens=("demo", "work", "-", "reload"),
                            recipe_path="inner.rx",
                            recipe_line=4,
                        ) as inner_chain:
                            assert outer_chain is not None
                            assert inner_chain is not None
                            assert [state.frame_id for state in frames.active_chains] == [
                                outer.id,
                                inner.id,
                            ]


def test_non_recipe_statement_does_not_create_checkpointable_chain_state() -> None:
    frames = ExecutionFrameStack()

    with frames.scope("statement"):
        with frames.chain_continuation_scope(
            statement_tokens=("demo", "one", "-", "demo", "two"),
            recipe_path=None,
            recipe_line=None,
        ) as state:
            assert state is None
            assert frames.active_chains == ()
