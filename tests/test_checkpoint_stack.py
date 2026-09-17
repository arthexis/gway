from __future__ import annotations

import json

import pytest

from gway.checkpoint import CheckpointError, CheckpointFlags, RecipeIdentity, ResumeCheckpoint
from gway.checkpoint.stack import (
    CONTINUATION_STACK_VERSION,
    ContinuationFrameCheckpoint,
    ContinuationStackCheckpoint,
)
from gway.provenance import ContinuationPoint, ValueProvenance


def _producer(frame_id: str, recipe: str, line: int) -> ValueProvenance:
    return ValueProvenance(
        frame_id=frame_id,
        frame_kind="operation",
        operation="demo",
        tokens=("demo", "produce"),
        recipe_path=recipe,
        recipe_line=line,
    )


def _frame(
    frame_id: str,
    parent_frame_id: str | None,
    recipe_path: str,
    sha: str,
    statement_index: int,
    line: int,
    next_statement_index: int | None,
    next_line: int | None,
) -> ContinuationFrameCheckpoint:
    producer = _producer(f"{frame_id}-producer", recipe_path, line)
    return ContinuationFrameCheckpoint(
        frame_id=frame_id,
        parent_frame_id=parent_frame_id,
        recipe=RecipeIdentity(recipe_path, sha),
        continuation=ContinuationPoint(
            recipe_path,
            statement_index,
            line,
            next_statement_index,
            next_line,
        ),
        context={"device": frame_id, "nested": [1, True, None]},
        context_provenance={"device": producer},
        has_previous_result=True,
        previous_result={"value": frame_id},
        previous_result_provenance=producer,
    )


def _stack() -> ContinuationStackCheckpoint:
    return ContinuationStackCheckpoint(
        frames=(
            _frame("frame-parent", None, "/recipes/parent.rx", "a" * 64, 2, 4, 3, 7),
            _frame(
                "frame-child",
                "frame-parent",
                "/recipes/child.rx",
                "b" * 64,
                1,
                2,
                2,
                5,
            ),
        ),
        flags=CheckpointFlags(interactive=True, explain=True, output_mode="json"),
    )


def test_stack_checkpoint_round_trip_is_deterministic() -> None:
    checkpoint = _stack()

    payload = checkpoint.to_json()
    restored = ContinuationStackCheckpoint.from_json(payload)

    assert restored == checkpoint
    assert restored.to_json() == payload
    decoded = json.loads(payload)
    assert decoded["version"] == CONTINUATION_STACK_VERSION
    assert [frame["frame_id"] for frame in decoded["frames"]] == [
        "frame-parent",
        "frame-child",
    ]


def test_stack_leaf_is_innermost_active_recipe() -> None:
    checkpoint = _stack()

    assert checkpoint.leaf.frame_id == "frame-child"
    assert checkpoint.leaf.parent_frame_id == "frame-parent"


def test_stack_rejects_empty_frames() -> None:
    with pytest.raises(CheckpointError, match="at least one frame"):
        ContinuationStackCheckpoint(frames=())


def test_stack_rejects_duplicate_frame_ids() -> None:
    root = _frame("same", None, "parent.rx", "a" * 64, 1, 1, 2, 2)
    child = _frame("same", "same", "child.rx", "b" * 64, 1, 1, 2, 2)

    with pytest.raises(CheckpointError, match="duplicate continuation frame id"):
        ContinuationStackCheckpoint(frames=(root, child))


def test_stack_rejects_root_parent() -> None:
    root = _frame("root", "other", "parent.rx", "a" * 64, 1, 1, 2, 2)

    with pytest.raises(CheckpointError, match="root continuation frame must not have a parent"):
        ContinuationStackCheckpoint(frames=(root,))


def test_stack_rejects_non_adjacent_parent_link() -> None:
    root = _frame("root", None, "parent.rx", "a" * 64, 1, 1, 2, 2)
    child = _frame("child", "wrong", "child.rx", "b" * 64, 1, 1, 2, 2)

    with pytest.raises(CheckpointError, match="parent does not match"):
        ContinuationStackCheckpoint(frames=(root, child))


def test_frame_reuses_v1_state_validation() -> None:
    with pytest.raises(CheckpointError, match="does not match"):
        ContinuationFrameCheckpoint(
            frame_id="frame-1",
            parent_frame_id=None,
            recipe=RecipeIdentity("recipe.rx", "a" * 64),
            continuation=ContinuationPoint("other.rx", 1, 1, None, None),
        )


def test_frame_detaches_caller_owned_state() -> None:
    context = {"nested": [1]}
    frame = ContinuationFrameCheckpoint(
        frame_id="frame-1",
        parent_frame_id=None,
        recipe=RecipeIdentity("recipe.rx", "a" * 64),
        continuation=ContinuationPoint("recipe.rx", 1, 1, None, None),
        context=context,
    )

    context["nested"].append(2)

    assert frame.context == {"nested": [1]}


def test_v1_checkpoint_normalizes_to_one_frame_v2_stack() -> None:
    producer = _producer("producer", "deploy.rx", 3)
    legacy = ResumeCheckpoint(
        recipe=RecipeIdentity("deploy.rx", "a" * 64),
        continuation=ContinuationPoint("deploy.rx", 2, 3, 3, 4),
        context={"device": "gway-004"},
        context_provenance={"device": producer},
        has_previous_result=True,
        previous_result="ok",
        previous_result_provenance=producer,
        flags=CheckpointFlags(interactive=True, explain=True),
    )

    normalized = ContinuationStackCheckpoint.from_json(legacy.to_json())

    assert normalized.version == CONTINUATION_STACK_VERSION
    assert len(normalized.frames) == 1
    assert normalized.leaf.frame_id == "legacy-frame-1"
    assert normalized.leaf.recipe == legacy.recipe
    assert normalized.leaf.continuation == legacy.continuation
    assert normalized.leaf.context == legacy.context
    assert normalized.flags == legacy.flags
    assert normalized.as_single_resume_checkpoint() == legacy


def test_multi_frame_stack_cannot_downgrade_to_single_resume_checkpoint() -> None:
    with pytest.raises(CheckpointError, match="multi-frame"):
        _stack().as_single_resume_checkpoint()


def test_stack_rejects_unknown_fields() -> None:
    raw = json.loads(_stack().to_json())
    raw["unexpected"] = True

    with pytest.raises(CheckpointError, match="unknown fields"):
        ContinuationStackCheckpoint.from_dict(raw)


def test_stack_rejects_unknown_frame_fields() -> None:
    raw = json.loads(_stack().to_json())
    raw["frames"][0]["unexpected"] = True

    with pytest.raises(CheckpointError, match="unknown fields"):
        ContinuationStackCheckpoint.from_dict(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interactive", "false"),
        ("interactive", 1),
        ("explain", "true"),
        ("explain", 0),
    ],
)
def test_stack_rejects_non_boolean_flags(field: str, value: object) -> None:
    raw = json.loads(_stack().to_json())
    raw["flags"][field] = value

    with pytest.raises(CheckpointError, match=rf"flags\.{field} must be a boolean"):
        ContinuationStackCheckpoint.from_dict(raw)


def test_stack_rejects_non_standard_json_numbers() -> None:
    payload = _stack().to_json().replace('"nested":[1,true,null]', '"nested":[NaN,true,null]', 1)

    with pytest.raises(CheckpointError, match="non-standard number NaN"):
        ContinuationStackCheckpoint.from_json(payload)
