from __future__ import annotations

import json
from pathlib import Path

import pytest

from gway.checkpoint import CheckpointError, CheckpointFlags, recipe_identity
from gway.checkpoint_chain import (
    CHAIN_CONTINUATION_VERSION,
    ChainContinuationCheckpoint,
    PendingChainCheckpoint,
    PendingStageCheckpoint,
)
from gway.checkpoint_stack import ContinuationFrameCheckpoint, ContinuationStackCheckpoint
from gway.provenance import ContinuationPoint, ValueProvenance
from gway.stage import StageKind, parse_stages


def _frame(
    recipe: Path,
    *,
    frame_id: str = "recipe-1",
    parent_frame_id: str | None = None,
    line: int = 1,
) -> ContinuationFrameCheckpoint:
    return ContinuationFrameCheckpoint(
        frame_id=frame_id,
        parent_frame_id=parent_frame_id,
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(
            recipe_path=str(recipe),
            statement_index=line,
            line=line,
            next_statement_index=None,
            next_line=None,
        ),
    )


def _chain(
    recipe: Path,
    *,
    frame_id: str = "recipe-1",
    line: int = 1,
    statement_tokens: tuple[str, ...] = ("demo", "produce", "-", "reload", "-", "demo", "consume"),
    active_stage_index: int = 2,
    has_previous_result: bool = True,
    previous_result: object = "before-reload",
    previous_result_provenance: ValueProvenance | None = None,
) -> PendingChainCheckpoint:
    stages = parse_stages(statement_tokens)
    return PendingChainCheckpoint(
        frame_id=frame_id,
        recipe_path=str(recipe),
        recipe_line=line,
        statement_tokens=statement_tokens,
        active_stage_index=active_stage_index,
        remaining_stages=tuple(
            PendingStageCheckpoint.from_stage(stage)
            for stage in stages[active_stage_index:]
        ),
        has_previous_result=has_previous_result,
        previous_result=previous_result if has_previous_result else None,  # type: ignore[arg-type]
        previous_result_provenance=previous_result_provenance,
    )


def test_version3_pending_chain_round_trip_is_deterministic(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("demo produce - reload - demo consume\n", encoding="utf-8")
    producer = ValueProvenance(
        frame_id="operation-1",
        frame_kind="operation",
        operation="demo",
        tokens=("demo", "produce"),
        recipe_path=str(recipe),
        recipe_line=1,
    )
    checkpoint = ChainContinuationCheckpoint(
        frames=(_frame(recipe),),
        pending_chains=(
            _chain(recipe, previous_result_provenance=producer),
        ),
        flags=CheckpointFlags(interactive=True, explain=True, output_mode="json"),
    )

    payload = checkpoint.to_json()
    restored = ChainContinuationCheckpoint.from_json(payload)

    assert restored == checkpoint
    assert restored.to_json() == payload
    assert restored.version == CHAIN_CONTINUATION_VERSION
    assert restored.pending_chains[0].previous_result_provenance == producer


def test_pending_stage_reconstructs_command_implicit_and_explicit_solve() -> None:
    stages = parse_stages(
        ("demo", "one", "-", "[device]", "-", "%", "prefix-[device]")
    )
    checkpoints = tuple(PendingStageCheckpoint.from_stage(stage) for stage in stages)

    assert [checkpoint.as_stage() for checkpoint in checkpoints] == list(stages)
    assert checkpoints[0].kind is StageKind.COMMAND
    assert checkpoints[1].kind is StageKind.SOLVE
    assert checkpoints[1].explicit_solve is False
    assert checkpoints[2].kind is StageKind.SOLVE
    assert checkpoints[2].explicit_solve is True


def test_pending_chain_rejects_remainder_that_disagrees_with_statement() -> None:
    statement = ("demo", "one", "-", "reload", "-", "demo", "two")
    wrong = PendingStageCheckpoint.from_stage(parse_stages(("demo", "wrong"))[0])

    with pytest.raises(CheckpointError, match="does not match statement_tokens"):
        PendingChainCheckpoint(
            frame_id="recipe-1",
            recipe_path="recipe.rx",
            recipe_line=1,
            statement_tokens=statement,
            active_stage_index=2,
            remaining_stages=(wrong,),
        )


@pytest.mark.parametrize("active_stage_index", [0, 4])
def test_pending_chain_rejects_invalid_active_stage_index(active_stage_index: int) -> None:
    statement = ("demo", "one", "-", "reload", "-", "demo", "two")

    with pytest.raises(CheckpointError, match="must identify a stage"):
        PendingChainCheckpoint(
            frame_id="recipe-1",
            recipe_path="recipe.rx",
            recipe_line=1,
            statement_tokens=statement,
            active_stage_index=active_stage_index,
            remaining_stages=(),
        )


def test_pending_chain_previous_result_is_detached_from_caller_state(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    result = {"nested": ["original"]}
    checkpoint = _chain(
        recipe,
        statement_tokens=("reload", "-", "demo", "consume"),
        active_stage_index=1,
        previous_result=result,
    )

    result["nested"].append("mutated")

    assert checkpoint.previous_result == {"nested": ["original"]}


def test_pending_chain_rejects_non_json_previous_result(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")

    with pytest.raises(CheckpointError, match="non-JSON value"):
        _chain(
            recipe,
            statement_tokens=("reload", "-", "demo", "consume"),
            active_stage_index=1,
            previous_result={"bad": object()},
        )


def test_pending_chain_rejects_provenance_without_previous_result(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    producer = ValueProvenance(frame_id="operation-1", frame_kind="operation")

    with pytest.raises(CheckpointError, match="requires has_previous_result"):
        _chain(
            recipe,
            statement_tokens=("reload", "-", "demo", "consume"),
            active_stage_index=1,
            has_previous_result=False,
            previous_result_provenance=producer,
        )


def test_version3_requires_at_least_one_pending_chain(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload\n", encoding="utf-8")

    with pytest.raises(CheckpointError, match="must contain pending chain state"):
        ChainContinuationCheckpoint(frames=(_frame(recipe),), pending_chains=())


def test_version3_rejects_unknown_or_duplicate_frame_links(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    frame = _frame(recipe)
    chain = _chain(
        recipe,
        statement_tokens=("reload", "-", "demo", "consume"),
        active_stage_index=1,
    )

    unknown = PendingChainCheckpoint(
        frame_id="missing",
        recipe_path=chain.recipe_path,
        recipe_line=chain.recipe_line,
        statement_tokens=chain.statement_tokens,
        active_stage_index=chain.active_stage_index,
        remaining_stages=chain.remaining_stages,
        has_previous_result=chain.has_previous_result,
        previous_result=chain.previous_result,
    )
    with pytest.raises(CheckpointError, match="unknown continuation frame"):
        ChainContinuationCheckpoint(frames=(frame,), pending_chains=(unknown,))

    with pytest.raises(CheckpointError, match="duplicate pending chain"):
        ChainContinuationCheckpoint(frames=(frame,), pending_chains=(chain, chain))


def test_pending_chains_follow_outer_to_inner_frame_order(tmp_path: Path) -> None:
    parent = tmp_path / "parent.rx"
    child = tmp_path / "child.rx"
    parent.write_text(f"recipe {child} - demo parent_done\n", encoding="utf-8")
    child.write_text("reload - demo child_done\n", encoding="utf-8")
    parent_frame = _frame(parent, frame_id="parent")
    child_frame = _frame(child, frame_id="child", parent_frame_id="parent")
    parent_chain = _chain(
        parent,
        frame_id="parent",
        statement_tokens=("recipe", str(child), "-", "demo", "parent_done"),
        active_stage_index=1,
    )
    child_chain = _chain(
        child,
        frame_id="child",
        statement_tokens=("reload", "-", "demo", "child_done"),
        active_stage_index=1,
    )

    with pytest.raises(CheckpointError, match="outer-to-inner order"):
        ChainContinuationCheckpoint(
            frames=(parent_frame, child_frame),
            pending_chains=(child_chain, parent_chain),
        )


def test_pending_chain_location_must_match_linked_recipe_frame(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    frame = _frame(recipe)
    chain = _chain(
        recipe,
        statement_tokens=("reload", "-", "demo", "consume"),
        active_stage_index=1,
    )

    wrong_path = PendingChainCheckpoint(
        frame_id=chain.frame_id,
        recipe_path="other.rx",
        recipe_line=chain.recipe_line,
        statement_tokens=chain.statement_tokens,
        active_stage_index=chain.active_stage_index,
        remaining_stages=chain.remaining_stages,
        has_previous_result=chain.has_previous_result,
        previous_result=chain.previous_result,
    )
    with pytest.raises(CheckpointError, match="recipe path"):
        ChainContinuationCheckpoint(frames=(frame,), pending_chains=(wrong_path,))

    wrong_line = PendingChainCheckpoint(
        frame_id=chain.frame_id,
        recipe_path=chain.recipe_path,
        recipe_line=2,
        statement_tokens=chain.statement_tokens,
        active_stage_index=chain.active_stage_index,
        remaining_stages=chain.remaining_stages,
        has_previous_result=chain.has_previous_result,
        previous_result=chain.previous_result,
    )
    with pytest.raises(CheckpointError, match="recipe line"):
        ChainContinuationCheckpoint(frames=(frame,), pending_chains=(wrong_line,))


def test_version3_parser_rejects_unknown_fields_and_nonstandard_numbers(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    checkpoint = ChainContinuationCheckpoint(
        frames=(_frame(recipe),),
        pending_chains=(
            _chain(
                recipe,
                statement_tokens=("reload", "-", "demo", "consume"),
                active_stage_index=1,
            ),
        ),
    )
    raw = checkpoint.as_dict()
    raw["unexpected"] = True

    with pytest.raises(CheckpointError, match="unknown fields"):
        ChainContinuationCheckpoint.from_json(json.dumps(raw))

    payload = checkpoint.to_json().replace('"active_stage_index":1', '"active_stage_index":NaN')
    with pytest.raises(CheckpointError, match="non-standard number"):
        ChainContinuationCheckpoint.from_json(payload)


def test_version3_wraps_existing_v2_stack_without_mutating_it(tmp_path: Path) -> None:
    recipe = tmp_path / "root.rx"
    recipe.write_text("reload - demo consume\n", encoding="utf-8")
    stack = ContinuationStackCheckpoint(
        frames=(_frame(recipe),),
        flags=CheckpointFlags(explain=True),
    )
    chain = _chain(
        recipe,
        statement_tokens=("reload", "-", "demo", "consume"),
        active_stage_index=1,
    )

    checkpoint = ChainContinuationCheckpoint.from_stack(
        stack,
        pending_chains=(chain,),
    )

    assert checkpoint.stack == stack
    assert checkpoint.flags.explain is True
    assert checkpoint.version == 3
