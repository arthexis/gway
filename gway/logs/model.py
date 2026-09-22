"""Structured records returned by GWAY logging operations."""

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class LogRecord:
    """One backend-neutral log entry normalized for GWAY callers."""

    timestamp: datetime
    source: str
    message: str
    level: str | None = None
    pid: int | None = None
    unit: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.timestamp, datetime):
            raise TypeError("LogRecord timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("LogRecord timestamp must be timezone-aware")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("LogRecord source cannot be empty")
        if not isinstance(self.message, str):
            raise TypeError("LogRecord message must be a string")

        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )
