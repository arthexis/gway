from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .checkpoint import (
    CHECKPOINT_VERSION,
    CheckpointError,
    CheckpointFlags,
    JSONValue,
    RecipeIdentity,
    ResumeCheckpoint,
)
from .provenance import ContinuationPoint, ValueProvenance

CONTINUATION_STACK_VERSION = 2


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"{label} must be a non-empty string")
    return value


def _optional_non_empty_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, label)


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CheckpointError(f"{label} must be a boolean")
    return value


def _expect_keys(raw: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(raw)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise CheckpointError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise CheckpointError(f"{label} has unknown fields: {', '.join(unknown)}")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckpointError(f"{label} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise CheckpointError(f"{label} keys must be strings")
    return value


def _frame_state_payload(frame: ContinuationFrameCheckpoint) -> dict[str, JSONValue]:
    legacy = ResumeCheckpoint(
        recipe=frame.recipe,
        continuation=frame.continuation,
        context=frame.context,
        context_provenance=frame.context_provenance,
        has_previous_result=frame.has_previous_result,
        previous_result=frame.previous_result,
        previous_result_provenance=frame.previous_result_provenance,
        flags=CheckpointFlags(),
    ).as_dict()
    legacy.pop("version")
    legacy.pop("flags")
    return legacy


@dataclass(frozen=True, slots=True)
class ContinuationFrameCheckpoint:
    """Serializable state for one active recipe invocation in a continuation stack."""

    frame_id: str
    parent_frame_id: str | None
    recipe: RecipeIdentity
    continuation: ContinuationPoint
    context: Mapping[str, JSONValue] = field(default_factory=dict)
    context_provenance: Mapping[str, ValueProvenance] = field(default_factory=dict)
    has_previous_result: bool = False
    previous_result: JSONValue = None
    previous_result_provenance: ValueProvenance | None = None

    def __post_init__(self) -> None:
        _non_empty_string(self.frame_id, "frame_id")
        _optional_non_empty_string(self.parent_frame_id, "parent_frame_id")

        validated = ResumeCheckpoint(
            recipe=self.recipe,
            continuation=self.continuation,
            context=self.context,
            context_provenance=self.context_provenance,
            has_previous_result=self.has_previous_result,
            previous_result=self.previous_result,
            previous_result_provenance=self.previous_result_provenance,
            flags=CheckpointFlags(),
        )
        object.__setattr__(self, "context", validated.context)
        object.__setattr__(self, "context_provenance", validated.context_provenance)
        object.__setattr__(self, "previous_result", validated.previous_result)

    def as_dict(self) -> dict[str, JSONValue]:
        payload = _frame_state_payload(self)
        return {
            "frame_id": self.frame_id,
            "parent_frame_id": self.parent_frame_id,
            **payload,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ContinuationFrameCheckpoint:
        expected = {
            "frame_id",
            "parent_frame_id",
            "recipe",
            "continuation",
            "context",
            "context_provenance",
            "has_previous_result",
            "previous_result",
            "previous_result_provenance",
        }
        _expect_keys(raw, expected, "continuation frame")
        legacy_raw = {
            "version": CHECKPOINT_VERSION,
            "recipe": raw["recipe"],
            "continuation": raw["continuation"],
            "context": raw["context"],
            "context_provenance": raw["context_provenance"],
            "has_previous_result": raw["has_previous_result"],
            "previous_result": raw["previous_result"],
            "previous_result_provenance": raw["previous_result_provenance"],
            "flags": CheckpointFlags().as_dict(),
        }
        state = ResumeCheckpoint.from_dict(legacy_raw)
        return cls(
            frame_id=_non_empty_string(raw["frame_id"], "frame_id"),
            parent_frame_id=_optional_non_empty_string(
                raw["parent_frame_id"], "parent_frame_id"
            ),
            recipe=state.recipe,
            continuation=state.continuation,
            context=state.context,
            context_provenance=state.context_provenance,
            has_previous_result=state.has_previous_result,
            previous_result=state.previous_result,
            previous_result_provenance=state.previous_result_provenance,
        )

    @classmethod
    def from_resume_checkpoint(
        cls,
        checkpoint: ResumeCheckpoint,
        *,
        frame_id: str,
        parent_frame_id: str | None = None,
    ) -> ContinuationFrameCheckpoint:
        return cls(
            frame_id=frame_id,
            parent_frame_id=parent_frame_id,
            recipe=checkpoint.recipe,
            continuation=checkpoint.continuation,
            context=checkpoint.context,
            context_provenance=checkpoint.context_provenance,
            has_previous_result=checkpoint.has_previous_result,
            previous_result=checkpoint.previous_result,
            previous_result_provenance=checkpoint.previous_result_provenance,
        )

    def as_resume_checkpoint(self, *, flags: CheckpointFlags) -> ResumeCheckpoint:
        return ResumeCheckpoint(
            recipe=self.recipe,
            continuation=self.continuation,
            context=self.context,
            context_provenance=self.context_provenance,
            has_previous_result=self.has_previous_result,
            previous_result=self.previous_result,
            previous_result_provenance=self.previous_result_provenance,
            flags=flags,
        )


@dataclass(frozen=True, slots=True)
class ContinuationStackCheckpoint:
    """Version-2 checkpoint containing the complete active recipe continuation stack."""

    frames: Sequence[ContinuationFrameCheckpoint]
    flags: CheckpointFlags = field(default_factory=CheckpointFlags)
    version: int = CONTINUATION_STACK_VERSION

    def __post_init__(self) -> None:
        if self.version != CONTINUATION_STACK_VERSION:
            raise CheckpointError(
                f"unsupported continuation stack version {self.version}; "
                f"expected {CONTINUATION_STACK_VERSION}"
            )
        if not isinstance(self.flags, CheckpointFlags):
            raise CheckpointError("flags must be CheckpointFlags")
        if isinstance(self.frames, (str, bytes, bytearray)) or not isinstance(
            self.frames, Sequence
        ):
            raise CheckpointError("frames must be an array")
        frames = tuple(self.frames)
        if not frames:
            raise CheckpointError("continuation stack must contain at least one frame")
        if not all(isinstance(frame, ContinuationFrameCheckpoint) for frame in frames):
            raise CheckpointError("frames must contain continuation frame checkpoints")

        seen: set[str] = set()
        for index, frame in enumerate(frames):
            if frame.frame_id in seen:
                raise CheckpointError(f"duplicate continuation frame id: {frame.frame_id}")
            seen.add(frame.frame_id)
            if index == 0:
                if frame.parent_frame_id is not None:
                    raise CheckpointError("root continuation frame must not have a parent")
            else:
                expected_parent = frames[index - 1].frame_id
                if frame.parent_frame_id != expected_parent:
                    raise CheckpointError(
                        "continuation frame parent does not match the preceding stack frame"
                    )
        object.__setattr__(self, "frames", frames)

    @property
    def leaf(self) -> ContinuationFrameCheckpoint:
        return self.frames[-1]

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "frames": [frame.as_dict() for frame in self.frames],
            "flags": self.flags.as_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ContinuationStackCheckpoint:
        _expect_keys(raw, {"version", "frames", "flags"}, "continuation stack checkpoint")
        version = raw["version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise CheckpointError("version must be an integer")
        if version != CONTINUATION_STACK_VERSION:
            raise CheckpointError(
                f"unsupported continuation stack version {version}; "
                f"expected {CONTINUATION_STACK_VERSION}"
            )
        frames_raw = raw["frames"]
        if not isinstance(frames_raw, list):
            raise CheckpointError("frames must be an array")
        frames = tuple(
            ContinuationFrameCheckpoint.from_dict(
                _require_mapping(frame, f"frames[{index}]")
            )
            for index, frame in enumerate(frames_raw)
        )
        flags_raw = _require_mapping(raw["flags"], "flags")
        _expect_keys(flags_raw, {"interactive", "explain", "output_mode"}, "flags")
        flags = CheckpointFlags(
            interactive=_require_bool(flags_raw["interactive"], "flags.interactive"),
            explain=_require_bool(flags_raw["explain"], "flags.explain"),
            output_mode=flags_raw["output_mode"],  # validated below by ResumeCheckpoint
        )
        flags_checkpoint = ResumeCheckpoint.from_dict(
            {
                "version": CHECKPOINT_VERSION,
                "recipe": frames[0].recipe.as_dict()
                if frames
                else {"path": "x", "sha256": "0" * 64},
                "continuation": frames[0].continuation.as_dict()
                if frames
                else {
                    "recipe_path": "x",
                    "statement_index": 1,
                    "line": 1,
                    "next_statement_index": None,
                    "next_line": None,
                },
                "context": {},
                "context_provenance": {},
                "has_previous_result": False,
                "previous_result": None,
                "previous_result_provenance": None,
                "flags": flags.as_dict(),
            }
        )
        return cls(frames=frames, flags=flags_checkpoint.flags, version=version)

    @classmethod
    def from_json(cls, payload: str) -> ContinuationStackCheckpoint:
        def reject_constant(value: str) -> object:
            raise CheckpointError(f"checkpoint contains non-standard number {value}")

        try:
            raw = json.loads(payload, parse_constant=reject_constant)
        except json.JSONDecodeError as exc:
            raise CheckpointError(f"invalid checkpoint JSON: {exc.msg}") from exc
        if not isinstance(raw, Mapping):
            raise CheckpointError("checkpoint JSON root must be an object")
        version = raw.get("version")
        if version == CHECKPOINT_VERSION:
            legacy = ResumeCheckpoint.from_dict(raw)
            return cls.from_resume_checkpoint(legacy)
        return cls.from_dict(raw)

    @classmethod
    def from_resume_checkpoint(
        cls,
        checkpoint: ResumeCheckpoint,
        *,
        frame_id: str = "legacy-frame-1",
    ) -> ContinuationStackCheckpoint:
        return cls(
            frames=(
                ContinuationFrameCheckpoint.from_resume_checkpoint(
                    checkpoint,
                    frame_id=frame_id,
                ),
            ),
            flags=checkpoint.flags,
        )

    def as_single_resume_checkpoint(self) -> ResumeCheckpoint:
        if len(self.frames) != 1:
            raise CheckpointError(
                "multi-frame continuation stack cannot be converted to a single resume checkpoint"
            )
        return self.frames[0].as_resume_checkpoint(flags=self.flags)


__all__ = [
    "CONTINUATION_STACK_VERSION",
    "ContinuationFrameCheckpoint",
    "ContinuationStackCheckpoint",
]
