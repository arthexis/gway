"""Structured rotating-file reader for portable GWAY logging."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from .model import LogRecord


class FileLogError(RuntimeError):
    """Raised when a structured rotating log cannot be read safely."""

    def __init__(self, message, *, path=None, line=None):
        super().__init__(message)
        self.path = None if path is None else Path(path)
        self.line = line


def _bound(value, label):
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()
        lowered = text.lower()
        now = datetime.now(timezone.utc)
        if lowered == "now":
            return now
        if lowered == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        relative = re.fullmatch(
            r"(\d+)\s+(second|minute|hour|day)s?\s+ago",
            lowered,
        )
        if relative is not None:
            amount = int(relative.group(1))
            unit = relative.group(2)
            return now - timedelta(**{unit + "s": amount})
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FileLogError(
                f"{label} must be ISO-8601 or a supported relative time"
            ) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise FileLogError(f"{label} must be timezone-aware")
    return result


def log_files(base_path):
    """Return retained rotated files followed by the current active file."""
    base = Path(base_path)
    parent = base.parent
    try:
        rotated = sorted(
            path
            for path in parent.glob(base.name + ".*")
            if path.is_file()
        )
    except OSError:
        rotated = []
    if base.is_file():
        rotated.append(base)
    return rotated


def _record(payload, *, path, line):
    try:
        timestamp = datetime.fromisoformat(
            str(payload["timestamp"]).replace("Z", "+00:00")
        )
        source = payload["source"]
        message = payload["message"]
    except (KeyError, TypeError, ValueError) as exc:
        raise FileLogError(
            f"invalid structured log record in {path}:{line}",
            path=path,
            line=line,
        ) from exc

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {
            "timestamp",
            "source",
            "message",
            "level",
            "pid",
            "unit",
        }
    }
    return LogRecord(
        timestamp=timestamp,
        source=source,
        message=message,
        level=payload.get("level"),
        pid=payload.get("pid"),
        unit=payload.get("unit"),
        metadata=metadata,
    )


def _records(path):
    """Yield complete structured rows while tolerating legacy text and active tails."""
    try:
        handle = Path(path).open("r", encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return

    with handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            # Pre-L8 files used a human-readable formatter. They remain
            # harmless during migration but cannot be reconstructed safely.
            if not stripped.startswith("{"):
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if not line.endswith("\n"):
                    # The active writer may still be completing the final row.
                    return
                raise FileLogError(
                    f"invalid structured log JSON in {path}:{number}",
                    path=path,
                    line=number,
                ) from exc
            if not isinstance(payload, dict):
                raise FileLogError(
                    f"invalid structured log JSON object in {path}:{number}",
                    path=path,
                    line=number,
                )
            yield _record(payload, path=path, line=number)


def read_file_logs(
    sources,
    *,
    paths,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
):
    """Read structured rotating logs into backend-neutral LogRecord values."""
    selected = list(sources)
    identities = {source.identity for source in selected}
    lower = _bound(since, "since")
    upper = _bound(until, "until")
    pattern = re.compile(grep) if grep is not None else None

    if limit is not None:
        limit = int(limit)
        if limit <= 0:
            raise ValueError("file log limit must be positive")

    records = []
    seen_paths = set()
    for base in paths:
        for path in log_files(base):
            resolved = Path(path)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            for record in _records(resolved):
                if identities and record.source not in identities:
                    continue
                if lower is not None and record.timestamp < lower:
                    continue
                if upper is not None and record.timestamp > upper:
                    continue
                if pattern is not None and pattern.search(record.message) is None:
                    continue
                records.append(record)

    records.sort(key=lambda item: item.timestamp, reverse=reverse)
    if limit is not None:
        records = records[:limit] if reverse else records[-limit:]
    return records
