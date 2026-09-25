from dataclasses import dataclass


@dataclass(frozen=True)
class AppSpec:
    name: str | None = None
