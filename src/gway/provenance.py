from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContinuationPoint:
    """Portable recipe run pointer describing current and pending work."""

    recipe_path: str
    statement_index: int
    line: int
    next_statement_index: int | None
    next_line: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "recipe_path": self.recipe_path,
            "statement_index": self.statement_index,
            "line": self.line,
            "next_statement_index": self.next_statement_index,
            "next_line": self.next_line,
        }


@dataclass(frozen=True, slots=True)
class ExecutionFrame:
    """Structural identity for one nested unit of GWAY execution."""

    id: str
    kind: str
    parent_id: str | None
    operation: str | None = None
    tokens: tuple[str, ...] = ()
    recipe_path: str | None = None
    recipe_line: int | None = None


@dataclass(frozen=True, slots=True)
class ValueProvenance:
    """Metadata describing the execution frame that produced a value."""

    frame_id: str
    frame_kind: str
    operation: str | None = None
    tokens: tuple[str, ...] = ()
    recipe_path: str | None = None
    recipe_line: int | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "frame_id": self.frame_id,
            "frame_kind": self.frame_kind,
        }
        if self.operation is not None:
            data["operation"] = self.operation
        if self.tokens:
            data["tokens"] = list(self.tokens)
        if self.recipe_path is not None:
            data["recipe_path"] = self.recipe_path
        if self.recipe_line is not None:
            data["recipe_line"] = self.recipe_line
        return data


@dataclass(frozen=True, slots=True)
class ActiveContinuation:
    """Live runtime state associated with one active recipe continuation."""

    frame_id: str
    point: ContinuationPoint
    context: MutableMapping[str, object]
    provenance: MutableMapping[str, ValueProvenance]


class ExecutionFrameStack:
    """Runtime-owned execution frame and recipe-continuation stack."""

    def __init__(self) -> None:
        self._frames: list[ExecutionFrame] = []
        self._history: dict[str, ExecutionFrame] = {}
        self._continuations: list[ContinuationPoint] = []
        self._active_continuations: list[ActiveContinuation] = []
        self._next_id = 1
        self._last_completed: ExecutionFrame | None = None

    @property
    def current(self) -> ExecutionFrame | None:
        return self._frames[-1] if self._frames else None

    @property
    def frames(self) -> tuple[ExecutionFrame, ...]:
        return tuple(self._frames)

    @property
    def last_completed(self) -> ExecutionFrame | None:
        return self._last_completed

    @property
    def current_continuation(self) -> ContinuationPoint | None:
        return self._continuations[-1] if self._continuations else None

    @property
    def continuations(self) -> tuple[ContinuationPoint, ...]:
        return tuple(self._continuations)

    @property
    def active_continuations(self) -> tuple[ActiveContinuation, ...]:
        """Return live continuation state from outermost to innermost recipe."""
        return tuple(self._active_continuations)

    def get(self, frame_id: str) -> ExecutionFrame | None:
        return self._history.get(frame_id)

    def value_provenance(self, frame: ExecutionFrame | None) -> ValueProvenance | None:
        if frame is None:
            return None
        operation = frame.operation
        recipe_path = frame.recipe_path
        recipe_line = frame.recipe_line
        ancestor = frame
        while ancestor.parent_id is not None and (recipe_path is None or recipe_line is None):
            parent = self.get(ancestor.parent_id)
            if parent is None:
                break
            if recipe_path is None:
                recipe_path = parent.recipe_path
            if recipe_line is None:
                recipe_line = parent.recipe_line
            ancestor = parent
        return ValueProvenance(
            frame_id=frame.id,
            frame_kind=frame.kind,
            operation=operation,
            tokens=frame.tokens,
            recipe_path=recipe_path,
            recipe_line=recipe_line,
        )

    @contextmanager
    def continuation_scope(
        self,
        point: ContinuationPoint,
        *,
        context: MutableMapping[str, object] | None = None,
        provenance: MutableMapping[str, ValueProvenance] | None = None,
    ) -> Iterator[ContinuationPoint]:
        """Push one active recipe pointer and optional serializable live state."""
        self._continuations.append(point)
        active: ActiveContinuation | None = None
        if context is not None:
            frame = self.current
            if frame is None or frame.kind != "recipe":
                raise RuntimeError("recipe continuation state requires an active recipe frame")
            active = ActiveContinuation(
                frame_id=frame.id,
                point=point,
                context=context,
                provenance={} if provenance is None else provenance,
            )
            self._active_continuations.append(active)
        try:
            yield point
        finally:
            if active is not None:
                popped_active = self._active_continuations.pop()
                if popped_active is not active:
                    raise RuntimeError("active recipe continuation stack was corrupted")
            popped = self._continuations.pop()
            if popped is not point:
                raise RuntimeError("recipe continuation stack was corrupted")

    @contextmanager
    def restored_scope(
        self,
        frame_id: str,
        kind: str,
        *,
        expected_parent_id: str | None,
        operation: str | None = None,
        tokens: Sequence[str] = (),
        recipe_path: str | None = None,
        recipe_line: int | None = None,
    ) -> Iterator[ExecutionFrame]:
        """Restore one serialized frame identity while preserving stack ancestry."""
        parent = self.current
        actual_parent_id = parent.id if parent is not None else None
        if actual_parent_id != expected_parent_id:
            raise RuntimeError("restored execution frame parent does not match active stack")
        if frame_id in self._history:
            raise RuntimeError(f"restored execution frame id is already in use: {frame_id}")
        frame = ExecutionFrame(
            id=frame_id,
            kind=kind,
            parent_id=actual_parent_id,
            operation=operation,
            tokens=tuple(tokens),
            recipe_path=recipe_path,
            recipe_line=recipe_line,
        )
        self._frames.append(frame)
        self._history[frame.id] = frame
        match = re.fullmatch(r"frame-(\d+)", frame.id)
        if match is not None:
            self._next_id = max(self._next_id, int(match.group(1)) + 1)
        try:
            yield frame
        finally:
            popped = self._frames.pop()
            if popped is not frame:
                raise RuntimeError("execution frame stack was corrupted")
            self._last_completed = frame

    @contextmanager
    def scope(
        self,
        kind: str,
        *,
        operation: str | None = None,
        tokens: Sequence[str] = (),
        recipe_path: str | None = None,
        recipe_line: int | None = None,
    ) -> Iterator[ExecutionFrame]:
        parent = self.current
        frame = ExecutionFrame(
            id=f"frame-{self._next_id}",
            kind=kind,
            parent_id=parent.id if parent is not None else None,
            operation=operation,
            tokens=tuple(tokens),
            recipe_path=recipe_path,
            recipe_line=recipe_line,
        )
        self._next_id += 1
        self._frames.append(frame)
        self._history[frame.id] = frame
        try:
            yield frame
        finally:
            popped = self._frames.pop()
            if popped is not frame:
                raise RuntimeError("execution frame stack was corrupted")
            self._last_completed = frame


def serialize_provenance(
    provenance: Mapping[str, ValueProvenance],
) -> dict[str, dict[str, object]]:
    return {key: value.as_dict() for key, value in provenance.items()}


__all__ = [
    "ActiveContinuation",
    "ContinuationPoint",
    "ExecutionFrame",
    "ExecutionFrameStack",
    "ValueProvenance",
    "serialize_provenance",
]
