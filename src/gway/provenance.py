from __future__ import annotations

from collections.abc import Iterator, Sequence
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


class ExecutionFrameStack:
    """Runtime-owned execution frame stack with deterministic local IDs."""

    def __init__(self) -> None:
        self._frames: list[ExecutionFrame] = []
        self._next_id = 1

    @property
    def current(self) -> ExecutionFrame | None:
        return self._frames[-1] if self._frames else None

    @property
    def frames(self) -> tuple[ExecutionFrame, ...]:
        return tuple(self._frames)

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
        try:
            yield frame
        finally:
            popped = self._frames.pop()
            if popped is not frame:
                raise RuntimeError("execution frame stack was corrupted")


__all__ = ["ExecutionFrame", "ExecutionFrameStack"]
