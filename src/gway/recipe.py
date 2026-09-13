from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .chain import run_statement
from .dispatcher import Dispatcher


@dataclass(slots=True)
class RecipeSession:
    """Execute multiple GWAY statements against one persistent named context."""

    dispatcher: Dispatcher
    context: dict[str, object] = field(default_factory=dict)

    def run(
        self,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
    ) -> object:
        return run_statement(
            self.dispatcher,
            tokens,
            interactive=interactive,
            context=self.context,
        )


__all__ = ["RecipeSession"]
