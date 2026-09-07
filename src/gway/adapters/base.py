from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from gway.command import Command
from gway.project import Project


class ProjectAdapter(Protocol):
    """Small framework-neutral contract implemented by project adapters."""

    project: Project

    def commands(self) -> Iterable[Command]: ...

    def describe(self, path: tuple[str, ...]) -> Command: ...

    def run(self, path: tuple[str, ...], argv: list[str]) -> object: ...
