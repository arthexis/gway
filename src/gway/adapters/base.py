from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, runtime_checkable

from gway.command import Command
from gway.project import Project


class ProjectAdapter(Protocol):
    """Small framework-neutral contract implemented by project adapters."""

    project: Project

    def commands(self) -> Iterable[Command]: ...

    def describe(self, path: tuple[str, ...]) -> Command: ...

    def run(self, path: tuple[str, ...], argv: list[str]) -> object: ...


@runtime_checkable
class SigilContextAdapter(Protocol):
    """Optional adapter capability for project-provided lazy Sigil context."""

    def sigil_context(self, command_path: tuple[str, ...]) -> Mapping[str, object]: ...
