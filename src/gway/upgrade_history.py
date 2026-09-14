from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import GwayPaths
from .repository import WorkingTreeEntry


@dataclass(frozen=True)
class UpgradeHistoryRecord:
    timestamp: str
    project: str
    repository: str
    checkout: str
    previous_revision: str | None
    resulting_revision: str | None
    force_used: bool
    force_error_type: str
    force_error: str
    forced_retry_succeeded: bool
    dirty_files: tuple[WorkingTreeEntry, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        project: str,
        repository: str,
        checkout: Path,
        previous_revision: str | None,
        resulting_revision: str | None,
        force_error_type: str,
        force_error: str,
        forced_retry_succeeded: bool,
        dirty_files: tuple[WorkingTreeEntry, ...] = (),
    ) -> UpgradeHistoryRecord:
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            project=project,
            repository=repository,
            checkout=str(checkout),
            previous_revision=previous_revision,
            resulting_revision=resulting_revision,
            force_used=True,
            force_error_type=force_error_type,
            force_error=force_error,
            forced_retry_succeeded=forced_retry_succeeded,
            dirty_files=dirty_files,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "project": self.project,
            "repository": self.repository,
            "checkout": self.checkout,
            "previous_revision": self.previous_revision,
            "resulting_revision": self.resulting_revision,
            "force_used": self.force_used,
            "force_error_type": self.force_error_type,
            "force_error": self.force_error,
            "forced_retry_succeeded": self.forced_retry_succeeded,
            "dirty_files": [
                {
                    "status": entry.status,
                    "path": entry.path,
                    "original_path": entry.original_path,
                }
                for entry in self.dirty_files
            ],
        }


def append_upgrade_history(paths: GwayPaths, record: UpgradeHistoryRecord) -> None:
    """Append one complete audit record using a single OS-level write."""
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    path = paths.data_dir / "upgrade-history.jsonl"
    payload = (json.dumps(record.as_dict(), separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    descriptor = os.open(path, flags, 0o600)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short write while appending upgrade history: {written}/{len(payload)}")
    finally:
        os.close(descriptor)
