from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass


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


class ExecutionFrameStack:
    """Runtime-owned execution frame stack with deterministic local IDs."""

    def __init__(self) -> None:
        self._frames: list[ExecutionFrame] = []
        self._history: dict[str, ExecutionFrame] = {}
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
    "ExecutionFrame",
    "ExecutionFrameStack",
    "ValueProvenance",
    "serialize_provenance",
]
