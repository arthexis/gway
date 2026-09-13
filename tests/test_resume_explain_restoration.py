from __future__ import annotations

from collections.abc import Callable, Sequence

from gway.chain import run_statement
from gway.explain import explain_scope
from gway.provenance import ContinuationPoint, ExecutionFrameStack, ValueProvenance
from gway.runtime import GwayRuntime
from gway.stage import Stage


def _producer() -> ValueProvenance:
    return ValueProvenance(
        frame_id="frame-before-reload",
        frame_kind="operation",
        operation="demo",
        tokens=("demo", "produce"),
        recipe_path="root.rx",
        recipe_line=4,
    )


def test_restored_frame_and_continuation_are_explicit_explain_events() -> None:
    frames = ExecutionFrameStack()
    point = ContinuationPoint(
        recipe_path="root.rx",
        statement_index=4,
        line=7,
        next_statement_index=5,
        next_line=9,
    )
    producer = _producer()

    with explain_scope() as trace:
        with frames.restored_scope(
            "frame-8",
            "recipe",
            expected_parent_id=None,
            recipe_path="root.rx",
        ) as frame:
            assert frames.is_restored(frame.id)
            frames.mark_restored_continuation(frame.id, point)
            with frames.continuation_scope(
                point,
                context={"device": "gway-004"},
                provenance={"device": producer},
            ):
                pass

    restored = next(step for step in trace if step.kind == "resume.frame.restore")
    assert restored.data["frame_id"] == "frame-8"
    assert restored.data["parent_frame_id"] is None
    assert restored.data["recipe_path"] == "root.rx"

    continuation = next(
        step for step in trace if step.kind == "resume.continuation.restore"
    )
    assert continuation.data["frame_id"] == "frame-8"
    assert continuation.data["statement_index"] == 4
    assert continuation.data["line"] == 7
    assert continuation.data["next_statement_index"] == 5
    assert continuation.data["next_line"] == 9
    assert (
        continuation.data["context_provenance"]["device"]["frame_id"]
        == "frame-before-reload"
    )


def test_restored_frame_does_not_mark_later_continuation_as_restored() -> None:
    frames = ExecutionFrameStack()
    restored = ContinuationPoint("root.rx", 1, 1, 2, 2)
    later = ContinuationPoint("root.rx", 2, 2, None, None)

    with explain_scope() as trace:
        with frames.restored_scope(
            "frame-8",
            "recipe",
            expected_parent_id=None,
            recipe_path="root.rx",
        ) as frame:
            frames.mark_restored_continuation(frame.id, restored)
            with frames.continuation_scope(restored, context={}, provenance={}):
                pass
            with frames.continuation_scope(later, context={}, provenance={}):
                pass

    continuations = [
        step for step in trace if step.kind == "resume.continuation.restore"
    ]
    assert len(continuations) == 1
    assert continuations[0].data["statement_index"] == 1


def test_fresh_frames_are_not_reported_as_restored() -> None:
    frames = ExecutionFrameStack()

    with explain_scope() as trace:
        with frames.scope("recipe", recipe_path="fresh.rx") as frame:
            assert not frames.is_restored(frame.id)

    assert not [step for step in trace if step.kind == "resume.frame.restore"]


class _ResumedRuntime(GwayRuntime):
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
        with self.frame_scope("operation", operation="demo", tokens=stage.raw_tokens):
            return transfer[0] if transfer else "empty"


def test_restored_chain_boundary_explains_saved_result_and_producer() -> None:
    runtime = _ResumedRuntime()
    producer = _producer()
    tokens = ("demo", "skipped", "-", "demo", "consume")

    with explain_scope() as trace:
        with runtime.frame_scope("statement", tokens=tokens):
            result = run_statement(
                runtime.dispatcher,
                tokens,
                runtime=runtime,
                start_stage_index=1,
                initial_result="saved",
                has_initial_result=True,
                initial_result_provenance=producer,
            )

    assert result == "saved"
    restored = next(step for step in trace if step.kind == "resume.chain.restore")
    assert restored.data["completed_stages"] == 1
    assert restored.data["next_stage_index"] == 2
    assert restored.data["total_stages"] == 2
    assert restored.data["has_previous_result"] is True
    assert restored.data["previous_result"] == "saved"
    assert (
        restored.data["previous_result_provenance"]["frame_id"]
        == "frame-before-reload"
    )

    completed = next(step for step in trace if step.kind == "resume.chain.result")
    assert completed.data["result"] == "saved"
    assert completed.data["provenance"]["operation"] == "demo"
