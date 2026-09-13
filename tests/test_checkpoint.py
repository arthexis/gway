from __future__ import annotations

import json

import pytest

from gway.checkpoint import (
    CHECKPOINT_VERSION,
    CheckpointError,
    CheckpointFlags,
    RecipeIdentity,
    ResumeCheckpoint,
    recipe_identity,
)
from gway.provenance import ContinuationPoint, ValueProvenance


def _checkpoint(**overrides: object) -> ResumeCheckpoint:
    recipe = RecipeIdentity("deploy.rx", "a" * 64)
    continuation = ContinuationPoint("deploy.rx", 2, 7, 3, 11)
    producer = ValueProvenance(
        frame_id="frame-4",
        frame_kind="operation",
        operation="demo",
        tokens=("demo", "produce"),
        recipe_path="deploy.rx",
        recipe_line=4,
    )
    values: dict[str, object] = {
        "recipe": recipe,
        "continuation": continuation,
        "context": {"device": "gway-004", "attempt": 2, "nested": [True, None]},
        "context_provenance": {"device": producer},
        "has_previous_result": True,
        "previous_result": None,
        "previous_result_provenance": producer,
        "flags": CheckpointFlags(interactive=True, explain=True, output_mode="json"),
    }
    values.update(overrides)
    return ResumeCheckpoint(**values)  # type: ignore[arg-type]


def test_checkpoint_json_round_trip_is_deterministic() -> None:
    checkpoint = _checkpoint()

    payload = checkpoint.to_json()
    restored = ResumeCheckpoint.from_json(payload)

    assert restored == checkpoint
    assert restored.to_json() == payload
    assert json.loads(payload)["version"] == CHECKPOINT_VERSION


def test_checkpoint_distinguishes_missing_result_from_null_result() -> None:
    with_result = _checkpoint(has_previous_result=True, previous_result=None)
    without_result = _checkpoint(
        has_previous_result=False,
        previous_result=None,
        previous_result_provenance=None,
    )

    assert ResumeCheckpoint.from_json(with_result.to_json()).has_previous_result is True
    assert ResumeCheckpoint.from_json(without_result.to_json()).has_previous_result is False


def test_checkpoint_rejects_non_json_values() -> None:
    with pytest.raises(CheckpointError, match="non-JSON value"):
        _checkpoint(context={"device": object()})

    with pytest.raises(CheckpointError, match="non-finite"):
        _checkpoint(context={"voltage": float("nan")})


def test_checkpoint_rejects_orphaned_provenance() -> None:
    producer = ValueProvenance(frame_id="frame-1", frame_kind="operation")

    with pytest.raises(CheckpointError, match="no matching value"):
        _checkpoint(context={}, context_provenance={"device": producer})


def test_checkpoint_requires_matching_recipe_identity_and_continuation() -> None:
    with pytest.raises(CheckpointError, match="does not match"):
        _checkpoint(continuation=ContinuationPoint("other.rx", 2, 7, 3, 11))


def test_checkpoint_rejects_incomplete_or_backward_next_pointer() -> None:
    with pytest.raises(CheckpointError, match="both be set"):
        _checkpoint(continuation=ContinuationPoint("deploy.rx", 2, 7, 3, None))

    with pytest.raises(CheckpointError, match="must follow"):
        _checkpoint(continuation=ContinuationPoint("deploy.rx", 2, 7, 2, 11))


def test_checkpoint_rejects_unsupported_version_before_other_fields() -> None:
    raw = json.loads(_checkpoint().to_json())
    raw["version"] = 99

    with pytest.raises(CheckpointError, match="unsupported checkpoint version 99"):
        ResumeCheckpoint.from_dict(raw)


def test_checkpoint_rejects_unknown_fields() -> None:
    raw = json.loads(_checkpoint().to_json())
    raw["unexpected"] = True

    with pytest.raises(CheckpointError, match="unknown fields: unexpected"):
        ResumeCheckpoint.from_dict(raw)


def test_checkpoint_rejects_non_standard_json_numbers() -> None:
    payload = _checkpoint().to_json().replace('"attempt":2', '"attempt":NaN')

    with pytest.raises(CheckpointError, match="non-standard number NaN"):
        ResumeCheckpoint.from_json(payload)


def test_recipe_identity_hashes_file_bytes(tmp_path) -> None:
    recipe = tmp_path / "deploy.rx"
    recipe.write_text("demo status\n", encoding="utf-8")

    identity = recipe_identity(recipe)

    assert identity.path == str(recipe)
    assert identity.sha256 == "fed132e63d43e9b2692079bfd3839f96b9a3c304cfd14134e49b30636cacc091"


def test_recipe_identity_requires_lowercase_sha256() -> None:
    with pytest.raises(CheckpointError, match="lowercase hexadecimal"):
        RecipeIdentity("deploy.rx", "A" * 64)
