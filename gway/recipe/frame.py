"""Live execution state for recipe invocations."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RecipeFrame:
    """Live resumable cursor for one active recipe invocation."""

    path: Path
    statements: list[list[object]]
    statement_index: int = 0
    pipeline_remaining: list[object] = field(default_factory=list)
    remaining_statements: list[list[object]] = field(default_factory=list)
    invocation_context: dict[str, object] = field(default_factory=dict)
    section: str | None = None
    environment: object | None = None
    requirements: dict[str, list[str]] = field(default_factory=dict)
    uv: Path | None = None
    preflight_requirements: dict[str, list[str]] = field(default_factory=dict)
    companion_worker: object | None = None
    companion_registered: bool = False

    def enter_statement(self, index):
        """Advance the cursor before one statement starts executing."""
        self.statement_index = int(index)
        self.pipeline_remaining = []
        self.remaining_statements = [
            list(statement) for statement in self.statements[index + 1 :]
        ]

    def set_pipeline_remaining(self, tokens):
        """Record the unexecuted tail of the current statement."""
        self.pipeline_remaining = list(tokens)
