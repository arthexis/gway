"""Declarative Sous Chef recipe jobs."""

from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEOUT = 15 * 60


@dataclass(frozen=True)
class Job:
    """Normalized Sous Chef recipe rule."""

    name: str
    root: Path
    recipe: Path
    every: float | None = None
    watch: Path | None = None
    down: str | None = None
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self):
        root = Path(self.root).expanduser().resolve()
        recipe = Path(self.recipe).expanduser().resolve()
        watch = (
            Path(self.watch).expanduser().resolve()
            if self.watch is not None
            else None
        )
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "recipe", recipe)
        object.__setattr__(self, "watch", watch)

    @property
    def triggers(self):
        """Return the configured one-word trigger names."""
        return tuple(
            name
            for name, value in (
                ("every", self.every),
                ("watch", self.watch),
                ("down", self.down),
            )
            if value is not None
        )
