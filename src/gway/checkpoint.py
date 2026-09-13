from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from .provenance import ContinuationPoint, ValueProvenance

CHECKPOINT_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class CheckpointError(ValueError):
    """Raised when checkpoint data cannot be safely represented or restored."""


@dataclass(frozen=True, slots=True)
class RecipeIdentity:
    """Stable identity for the recipe source expected at resume time."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.path:
            raise CheckpointError("recipe path must not be empty")
        if _SHA256.fullmatch(self.sha256) is None:
            raise CheckpointError("recipe sha256 must be 64 lowercase hexadecimal characters")

    def as_dict(self) -> dict[str, JSONValue]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class CheckpointFlags:
    """Execution options that must survive a process replacement."""

    interactive: bool = False
    explain: bool = False
    output_mode: str | None = None

    def __post_init__(self) -> None:
        if self.output_mode is not None and not self.output_mode:
            raise CheckpointError("output mode must be non-empty when provided")

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "interactive": self.interactive,
            "explain": self.explain,
            "output_mode": self.output_mode,
        }


@dataclass(frozen=True, slots=True)
class ResumeCheckpoint:
    """Versioned, JSON-safe state required to continue one active recipe."""

    recipe: RecipeIdentity
    continuation: ContinuationPoint
    context: Mapping[str, JSONValue] = field(default_factory=dict)
    context_provenance: Mapping[str, ValueProvenance] = field(default_factory=dict)
    has_previous_result: bool = False
    previous_result: JSONValue = None
    previous_result_provenance: ValueProvenance | None = None
    flags: CheckpointFlags = field(default_factory=CheckpointFlags)
    version: int = CHECKPOINT_VERSION

    def __post_init__(self) -> None:
        if self.version != CHECKPOINT_VERSION:
            raise CheckpointError(
                f"unsupported checkpoint version {self.version}; expected {CHECKPOINT_VERSION}"
            )
        _validate_continuation(self.continuation)
        if self.continuation.recipe_path != self.recipe.path:
            raise CheckpointError("continuation recipe path does not match recipe identity")
        _validate_json_mapping(self.context, "context")
        orphaned = set(self.context_provenance) - set(self.context)
        if orphaned:
            names = ", ".join(sorted(orphaned))
            raise CheckpointError(f"context provenance has no matching value: {names}")
        if not self.has_previous_result:
            if self.previous_result is not None:
                raise CheckpointError("previous result must be null when has_previous_result is false")
            if self.previous_result_provenance is not None:
                raise CheckpointError(
                    "previous result provenance requires has_previous_result to be true"
                )
        else:
            _validate_json_value(self.previous_result, "previous_result")

    def as_dict(self) -> dict[str, JSONValue]:
        """Return the canonical JSON object for checkpoint version 1."""
        context = {
            key: _copy_json_value(value)
            for key, value in self.context.items()
        }
        return {
            "version": self.version,
            "recipe": self.recipe.as_dict(),
            "continuation": _continuation_dict(self.continuation),
            "context": context,
            "context_provenance": {
                key: _provenance_dict(value)
                for key, value in self.context_provenance.items()
            },
            "has_previous_result": self.has_previous_result,
            "previous_result": _copy_json_value(self.previous_result),
            "previous_result_provenance": (
                _provenance_dict(self.previous_result_provenance)
                if self.previous_result_provenance is not None
                else None
            ),
            "flags": self.flags.as_dict(),
        }

    def to_json(self) -> str:
        """Serialize the checkpoint deterministically without non-standard JSON values."""
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ResumeCheckpoint:
        """Validate and construct one checkpoint from decoded JSON data."""
        _expect_keys(
            raw,
            {
                "version",
                "recipe",
                "continuation",
                "context",
                "context_provenance",
                "has_previous_result",
                "previous_result",
                "previous_result_provenance",
                "flags",
            },
            "checkpoint",
        )
        version = _require_int(raw["version"], "version")
        if version != CHECKPOINT_VERSION:
            raise CheckpointError(
                f"unsupported checkpoint version {version}; expected {CHECKPOINT_VERSION}"
            )
        recipe = _parse_recipe(_require_mapping(raw["recipe"], "recipe"))
        continuation = _parse_continuation(
            _require_mapping(raw["continuation"], "continuation")
        )
        context_raw = _require_mapping(raw["context"], "context")
        context = _parse_json_mapping(context_raw, "context")
        provenance_raw = _require_mapping(raw["context_provenance"], "context_provenance")
        context_provenance = {
            key: _parse_provenance(
                _require_mapping(value, f"context_provenance.{key}"),
                f"context_provenance.{key}",
            )
            for key, value in provenance_raw.items()
            if _require_string_key(key, "context_provenance")
        }
        has_previous_result = _require_bool(
            raw["has_previous_result"], "has_previous_result"
        )
        previous_result = _parse_json_value(raw["previous_result"], "previous_result")
        previous_provenance_raw = raw["previous_result_provenance"]
        previous_result_provenance = (
            None
            if previous_provenance_raw is None
            else _parse_provenance(
                _require_mapping(
                    previous_provenance_raw, "previous_result_provenance"
                ),
                "previous_result_provenance",
            )
        )
        flags = _parse_flags(_require_mapping(raw["flags"], "flags"))
        return cls(
            version=version,
            recipe=recipe,
            continuation=continuation,
            context=context,
            context_provenance=context_provenance,
            has_previous_result=has_previous_result,
            previous_result=previous_result,
            previous_result_provenance=previous_result_provenance,
            flags=flags,
        )

    @classmethod
    def from_json(cls, payload: str) -> ResumeCheckpoint:
        """Decode strict JSON and validate it as a checkpoint."""
        try:
            raw = json.loads(payload, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, CheckpointError) as exc:
            if isinstance(exc, CheckpointError):
                raise
            raise CheckpointError(f"invalid checkpoint JSON: {exc.msg}") from exc
        if not isinstance(raw, Mapping):
            raise CheckpointError("checkpoint JSON root must be an object")
        return cls.from_dict(raw)


def recipe_identity(path: str | Path) -> RecipeIdentity:
    """Hash one recipe file for later identity validation."""
    import hashlib

    recipe_path = Path(path)
    digest = hashlib.sha256(recipe_path.read_bytes()).hexdigest()
    return RecipeIdentity(path=str(recipe_path), sha256=digest)


def _validate_continuation(point: ContinuationPoint) -> None:
    if point.statement_index < 1 or point.line < 1:
        raise CheckpointError("continuation statement index and line must be positive")
    next_index = point.next_statement_index
    next_line = point.next_line
    if (next_index is None) != (next_line is None):
        raise CheckpointError("next statement index and line must either both be set or both be null")
    if next_index is not None:
        if next_index <= point.statement_index:
            raise CheckpointError("next statement index must follow the current statement")
        if next_line is None or next_line < 1:
            raise CheckpointError("next statement line must be positive")


def _continuation_dict(point: ContinuationPoint) -> dict[str, JSONValue]:
    return {
        "recipe_path": point.recipe_path,
        "statement_index": point.statement_index,
        "line": point.line,
        "next_statement_index": point.next_statement_index,
        "next_line": point.next_line,
    }


def _parse_recipe(raw: Mapping[str, object]) -> RecipeIdentity:
    _expect_keys(raw, {"path", "sha256"}, "recipe")
    return RecipeIdentity(
        path=_require_str(raw["path"], "recipe.path"),
        sha256=_require_str(raw["sha256"], "recipe.sha256"),
    )


def _parse_continuation(raw: Mapping[str, object]) -> ContinuationPoint:
    _expect_keys(
        raw,
        {
            "recipe_path",
            "statement_index",
            "line",
            "next_statement_index",
            "next_line",
        },
        "continuation",
    )
    point = ContinuationPoint(
        recipe_path=_require_str(raw["recipe_path"], "continuation.recipe_path"),
        statement_index=_require_int(raw["statement_index"], "continuation.statement_index"),
        line=_require_int(raw["line"], "continuation.line"),
        next_statement_index=_optional_int(
            raw["next_statement_index"], "continuation.next_statement_index"
        ),
        next_line=_optional_int(raw["next_line"], "continuation.next_line"),
    )
    _validate_continuation(point)
    return point


def _provenance_dict(value: ValueProvenance) -> dict[str, JSONValue]:
    return {
        "frame_id": value.frame_id,
        "frame_kind": value.frame_kind,
        "operation": value.operation,
        "tokens": list(value.tokens),
        "recipe_path": value.recipe_path,
        "recipe_line": value.recipe_line,
    }


def _parse_provenance(raw: Mapping[str, object], label: str) -> ValueProvenance:
    _expect_keys(
        raw,
        {"frame_id", "frame_kind", "operation", "tokens", "recipe_path", "recipe_line"},
        label,
    )
    tokens = raw["tokens"]
    if not isinstance(tokens, list) or not all(isinstance(token, str) for token in tokens):
        raise CheckpointError(f"{label}.tokens must be an array of strings")
    return ValueProvenance(
        frame_id=_require_str(raw["frame_id"], f"{label}.frame_id"),
        frame_kind=_require_str(raw["frame_kind"], f"{label}.frame_kind"),
        operation=_optional_str(raw["operation"], f"{label}.operation"),
        tokens=tuple(tokens),
        recipe_path=_optional_str(raw["recipe_path"], f"{label}.recipe_path"),
        recipe_line=_optional_int(raw["recipe_line"], f"{label}.recipe_line"),
    )


def _parse_flags(raw: Mapping[str, object]) -> CheckpointFlags:
    _expect_keys(raw, {"interactive", "explain", "output_mode"}, "flags")
    return CheckpointFlags(
        interactive=_require_bool(raw["interactive"], "flags.interactive"),
        explain=_require_bool(raw["explain"], "flags.explain"),
        output_mode=_optional_str(raw["output_mode"], "flags.output_mode"),
    )


def _validate_json_mapping(values: Mapping[str, object], label: str) -> None:
    for key, value in values.items():
        _require_string_key(key, label)
        _validate_json_value(value, f"{label}.{key}")


def _validate_json_value(value: object, label: str) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CheckpointError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]")
        return
    if isinstance(value, Mapping):
        _validate_json_mapping(value, label)
        return
    raise CheckpointError(f"{label} contains non-JSON value of type {type(value).__name__}")


def _parse_json_mapping(raw: Mapping[object, object], label: str) -> dict[str, JSONValue]:
    parsed: dict[str, JSONValue] = {}
    for key, value in raw.items():
        key = _require_string_key(key, label)
        parsed[key] = _parse_json_value(value, f"{label}.{key}")
    return parsed


def _parse_json_value(value: object, label: str) -> JSONValue:
    _validate_json_value(value, label)
    return _copy_json_value(value)


def _copy_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_copy_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _copy_json_value(item) for key, item in value.items()}
    raise CheckpointError(f"cannot copy non-JSON value of type {type(value).__name__}")


def _expect_keys(raw: Mapping[str, object], expected: set[str], label: str) -> None:
    keys = set(raw)
    missing = expected - keys
    extra = keys - expected
    if missing:
        raise CheckpointError(f"{label} is missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise CheckpointError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckpointError(f"{label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise CheckpointError(f"{label} keys must be strings")
    return value


def _require_string_key(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise CheckpointError(f"{label} keys must be strings")
    return value


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"{label} must be a non-empty string")
    return value


def _optional_str(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, label)


def _require_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CheckpointError(f"{label} must be an integer")
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, label)


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CheckpointError(f"{label} must be a boolean")
    return value


def _reject_json_constant(value: str) -> object:
    raise CheckpointError(f"checkpoint JSON contains non-standard number {value}")


__all__ = [
    "CHECKPOINT_VERSION",
    "CheckpointError",
    "CheckpointFlags",
    "JSONValue",
    "RecipeIdentity",
    "ResumeCheckpoint",
    "recipe_identity",
]
