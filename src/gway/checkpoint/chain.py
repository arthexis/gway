from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..provenance import ContinuationPoint, ValueProvenance
from ..stage import Stage, StageKind, StageSyntaxError, classify_stage, parse_stages
from .model import (
    CHECKPOINT_VERSION,
    CheckpointError,
    CheckpointFlags,
    JSONValue,
    RecipeIdentity,
    ResumeCheckpoint,
)
from .stack import (
    CONTINUATION_STACK_VERSION,
    ContinuationFrameCheckpoint,
    ContinuationStackCheckpoint,
)

CHAIN_CONTINUATION_VERSION = 3


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


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CheckpointError(f"{label} must be an integer")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CheckpointError(f"{label} must be a boolean")
    return value


def _require_string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CheckpointError(f"{label} must be an array of strings")
    return tuple(value)


def _dummy_resume_state(*, has_previous_result: bool, previous_result: JSONValue, previous_result_provenance: ValueProvenance | None) -> ResumeCheckpoint:
    path = "pending-chain"
    return ResumeCheckpoint(
        recipe=RecipeIdentity(path=path, sha256="0" * 64),
        continuation=ContinuationPoint(recipe_path=path, statement_index=1, line=1, next_statement_index=None, next_line=None),
        has_previous_result=has_previous_result,
        previous_result=previous_result,
        previous_result_provenance=previous_result_provenance,
        flags=CheckpointFlags(),
    )


@dataclass(frozen=True, slots=True)
class PendingStageCheckpoint:
    raw_tokens: Sequence[str]
    kind: StageKind
    explicit_solve: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.raw_tokens, (str, bytes, bytearray)) or not isinstance(self.raw_tokens, Sequence):
            raise CheckpointError("pending stage raw_tokens must be an array")
        raw_tokens = tuple(self.raw_tokens)
        if not raw_tokens or not all(isinstance(token, str) for token in raw_tokens):
            raise CheckpointError("pending stage raw_tokens must contain strings")
        if not isinstance(self.kind, StageKind):
            raise CheckpointError("pending stage kind must be a StageKind")
        if not isinstance(self.explicit_solve, bool):
            raise CheckpointError("pending stage explicit_solve must be a boolean")
        source_tokens = ("%", *raw_tokens) if self.explicit_solve else raw_tokens
        try:
            parsed = classify_stage(source_tokens)
        except StageSyntaxError as exc:
            raise CheckpointError(f"invalid pending stage: {exc}") from exc
        if parsed.kind is not self.kind or parsed.explicit_solve is not self.explicit_solve:
            raise CheckpointError("pending stage metadata does not match its raw tokens")
        object.__setattr__(self, "raw_tokens", raw_tokens)

    @classmethod
    def from_stage(cls, stage: Stage) -> PendingStageCheckpoint:
        return cls(raw_tokens=stage.raw_tokens, kind=stage.kind, explicit_solve=stage.explicit_solve)

    def as_stage(self) -> Stage:
        source_tokens = ("%", *self.raw_tokens) if self.explicit_solve else self.raw_tokens
        return classify_stage(source_tokens)

    def as_dict(self) -> dict[str, JSONValue]:
        return {"raw_tokens": list(self.raw_tokens), "kind": self.kind.value, "explicit_solve": self.explicit_solve}

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> PendingStageCheckpoint:
        _expect_keys(raw, {"raw_tokens", "kind", "explicit_solve"}, "pending stage")
        kind_raw = _require_string(raw["kind"], "pending stage.kind")
        try:
            kind = StageKind(kind_raw)
        except ValueError as exc:
            raise CheckpointError(f"unsupported pending stage kind: {kind_raw}") from exc
        return cls(
            raw_tokens=_require_string_array(raw["raw_tokens"], "pending stage.raw_tokens"),
            kind=kind,
            explicit_solve=_require_bool(raw["explicit_solve"], "pending stage.explicit_solve"),
        )


@dataclass(frozen=True, slots=True)
class PendingChainCheckpoint:
    frame_id: str
    recipe_path: str
    recipe_line: int
    statement_tokens: Sequence[str]
    active_stage_index: int
    remaining_stages: Sequence[PendingStageCheckpoint]
    has_previous_result: bool = False
    previous_result: JSONValue = None
    previous_result_provenance: ValueProvenance | None = None

    def __post_init__(self) -> None:
        _require_string(self.frame_id, "pending chain.frame_id")
        _require_string(self.recipe_path, "pending chain.recipe_path")
        if _require_int(self.recipe_line, "pending chain.recipe_line") < 1:
            raise CheckpointError("pending chain.recipe_line must be positive")
        if isinstance(self.statement_tokens, (str, bytes, bytearray)) or not isinstance(self.statement_tokens, Sequence):
            raise CheckpointError("pending chain.statement_tokens must be an array")
        statement_tokens = tuple(self.statement_tokens)
        if not statement_tokens or not all(isinstance(token, str) for token in statement_tokens):
            raise CheckpointError("pending chain.statement_tokens must contain strings")
        active_stage_index = _require_int(self.active_stage_index, "pending chain.active_stage_index")
        try:
            parsed_stages = parse_stages(statement_tokens)
        except StageSyntaxError as exc:
            raise CheckpointError(f"invalid pending chain statement: {exc}") from exc
        if active_stage_index < 1 or active_stage_index > len(parsed_stages):
            raise CheckpointError("pending chain.active_stage_index must identify a stage in statement_tokens")
        if isinstance(self.remaining_stages, (str, bytes, bytearray)) or not isinstance(self.remaining_stages, Sequence):
            raise CheckpointError("pending chain.remaining_stages must be an array")
        remaining_stages = tuple(self.remaining_stages)
        if not all(isinstance(stage, PendingStageCheckpoint) for stage in remaining_stages):
            raise CheckpointError("pending chain.remaining_stages must contain pending stage checkpoints")
        expected = tuple(PendingStageCheckpoint.from_stage(stage) for stage in parsed_stages[active_stage_index:])
        if remaining_stages != expected:
            raise CheckpointError("pending chain.remaining_stages does not match statement_tokens after the active stage")
        has_previous_result = _require_bool(self.has_previous_result, "pending chain.has_previous_result")
        validated = _dummy_resume_state(
            has_previous_result=has_previous_result,
            previous_result=self.previous_result,
            previous_result_provenance=self.previous_result_provenance,
        )
        object.__setattr__(self, "statement_tokens", statement_tokens)
        object.__setattr__(self, "remaining_stages", remaining_stages)
        object.__setattr__(self, "previous_result", validated.previous_result)

    def as_dict(self) -> dict[str, JSONValue]:
        validated = _dummy_resume_state(
            has_previous_result=self.has_previous_result,
            previous_result=self.previous_result,
            previous_result_provenance=self.previous_result_provenance,
        ).as_dict()
        return {
            "frame_id": self.frame_id,
            "recipe_path": self.recipe_path,
            "recipe_line": self.recipe_line,
            "statement_tokens": list(self.statement_tokens),
            "active_stage_index": self.active_stage_index,
            "remaining_stages": [stage.as_dict() for stage in self.remaining_stages],
            "has_previous_result": self.has_previous_result,
            "previous_result": validated["previous_result"],
            "previous_result_provenance": validated["previous_result_provenance"],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> PendingChainCheckpoint:
        _expect_keys(raw, {"frame_id", "recipe_path", "recipe_line", "statement_tokens", "active_stage_index", "remaining_stages", "has_previous_result", "previous_result", "previous_result_provenance"}, "pending chain")
        remaining_raw = raw["remaining_stages"]
        if not isinstance(remaining_raw, list):
            raise CheckpointError("pending chain.remaining_stages must be an array")
        previous_provenance = raw["previous_result_provenance"]
        parsed_previous_provenance: ValueProvenance | None = None
        if previous_provenance is not None:
            dummy = ResumeCheckpoint.from_dict({
                "version": CHECKPOINT_VERSION,
                "recipe": {"path": "pending-chain", "sha256": "0" * 64},
                "continuation": {"recipe_path": "pending-chain", "statement_index": 1, "line": 1, "next_statement_index": None, "next_line": None},
                "context": {},
                "context_provenance": {},
                "has_previous_result": True,
                "previous_result": raw["previous_result"],
                "previous_result_provenance": previous_provenance,
                "flags": CheckpointFlags().as_dict(),
            })
            parsed_previous_provenance = dummy.previous_result_provenance
            previous_result = dummy.previous_result
        else:
            previous_result = raw["previous_result"]
        return cls(
            frame_id=_require_string(raw["frame_id"], "pending chain.frame_id"),
            recipe_path=_require_string(raw["recipe_path"], "pending chain.recipe_path"),
            recipe_line=_require_int(raw["recipe_line"], "pending chain.recipe_line"),
            statement_tokens=_require_string_array(raw["statement_tokens"], "pending chain.statement_tokens"),
            active_stage_index=_require_int(raw["active_stage_index"], "pending chain.active_stage_index"),
            remaining_stages=tuple(PendingStageCheckpoint.from_dict(_require_mapping(stage, f"pending chain.remaining_stages[{index}]")) for index, stage in enumerate(remaining_raw)),
            has_previous_result=_require_bool(raw["has_previous_result"], "pending chain.has_previous_result"),
            previous_result=previous_result,
            previous_result_provenance=parsed_previous_provenance,
        )


@dataclass(frozen=True, slots=True)
class ChainContinuationCheckpoint:
    frames: Sequence[ContinuationFrameCheckpoint]
    pending_chains: Sequence[PendingChainCheckpoint]
    flags: CheckpointFlags = field(default_factory=CheckpointFlags)
    version: int = CHAIN_CONTINUATION_VERSION

    def __post_init__(self) -> None:
        if self.version != CHAIN_CONTINUATION_VERSION:
            raise CheckpointError(f"unsupported chain continuation version {self.version}; expected {CHAIN_CONTINUATION_VERSION}")
        stack = ContinuationStackCheckpoint(frames=self.frames, flags=self.flags)
        frames = tuple(stack.frames)
        if isinstance(self.pending_chains, (str, bytes, bytearray)) or not isinstance(self.pending_chains, Sequence):
            raise CheckpointError("pending_chains must be an array")
        pending_chains = tuple(self.pending_chains)
        if not pending_chains:
            raise CheckpointError("version 3 checkpoint must contain pending chain state")
        if not all(isinstance(chain, PendingChainCheckpoint) for chain in pending_chains):
            raise CheckpointError("pending_chains must contain pending chain checkpoints")
        frame_positions = {frame.frame_id: index for index, frame in enumerate(frames)}
        seen: set[str] = set()
        previous_position = -1
        for chain in pending_chains:
            if chain.frame_id in seen:
                raise CheckpointError(f"duplicate pending chain for continuation frame: {chain.frame_id}")
            seen.add(chain.frame_id)
            position = frame_positions.get(chain.frame_id)
            if position is None:
                raise CheckpointError(f"pending chain references unknown continuation frame: {chain.frame_id}")
            if position <= previous_position:
                raise CheckpointError("pending_chains must follow the same outer-to-inner order as frames")
            previous_position = position
            frame = frames[position]
            if chain.recipe_path != frame.continuation.recipe_path:
                raise CheckpointError("pending chain recipe path does not match its continuation frame")
            if chain.recipe_line != frame.continuation.line:
                raise CheckpointError("pending chain recipe line does not match its continuation frame")
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "pending_chains", pending_chains)
        object.__setattr__(self, "flags", stack.flags)

    @property
    def stack(self) -> ContinuationStackCheckpoint:
        return ContinuationStackCheckpoint(frames=self.frames, flags=self.flags)

    def as_dict(self) -> dict[str, JSONValue]:
        return {"version": self.version, "frames": [frame.as_dict() for frame in self.frames], "pending_chains": [chain.as_dict() for chain in self.pending_chains], "flags": self.flags.as_dict()}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ChainContinuationCheckpoint:
        _expect_keys(raw, {"version", "frames", "pending_chains", "flags"}, "chain continuation checkpoint")
        version = _require_int(raw["version"], "version")
        if version != CHAIN_CONTINUATION_VERSION:
            raise CheckpointError(f"unsupported chain continuation version {version}; expected {CHAIN_CONTINUATION_VERSION}")
        stack = ContinuationStackCheckpoint.from_dict({"version": CONTINUATION_STACK_VERSION, "frames": raw["frames"], "flags": raw["flags"]})
        pending_raw = raw["pending_chains"]
        if not isinstance(pending_raw, list):
            raise CheckpointError("pending_chains must be an array")
        pending_chains = tuple(PendingChainCheckpoint.from_dict(_require_mapping(chain, f"pending_chains[{index}]")) for index, chain in enumerate(pending_raw))
        return cls(frames=stack.frames, pending_chains=pending_chains, flags=stack.flags, version=version)

    @classmethod
    def from_json(cls, payload: str) -> ChainContinuationCheckpoint:
        def reject_constant(value: str) -> object:
            raise CheckpointError(f"checkpoint contains non-standard number {value}")
        try:
            raw = json.loads(payload, parse_constant=reject_constant)
        except json.JSONDecodeError as exc:
            raise CheckpointError(f"invalid checkpoint JSON: {exc.msg}") from exc
        if not isinstance(raw, Mapping):
            raise CheckpointError("checkpoint JSON root must be an object")
        return cls.from_dict(raw)

    @classmethod
    def from_stack(cls, stack: ContinuationStackCheckpoint, *, pending_chains: Sequence[PendingChainCheckpoint]) -> ChainContinuationCheckpoint:
        return cls(frames=stack.frames, pending_chains=pending_chains, flags=stack.flags)


__all__ = ["CHAIN_CONTINUATION_VERSION", "ChainContinuationCheckpoint", "PendingChainCheckpoint", "PendingStageCheckpoint"]
