"""Descriptive logical sources for GWAY log selection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LogSource:
    """Describe one selectable logical log source without querying it."""

    identity: str
    kind: str
    project: str | None = None
    service: str | None = None
    backend: str | None = None
    backend_id: str | None = None
    system: bool | None = None

    def __post_init__(self):
        identity = self.identity.strip() if isinstance(self.identity, str) else ""
        kind = self.kind.strip() if isinstance(self.kind, str) else ""
        if not identity:
            raise ValueError("LogSource identity cannot be empty")
        if not kind:
            raise ValueError("LogSource kind cannot be empty")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "kind", kind)
