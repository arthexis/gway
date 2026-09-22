"""Bounded journald reads for concrete systemd-backed log sources."""

from datetime import datetime, timezone
import json
import subprocess

from .model import LogRecord


JOURNALCTL_TIMEOUT = 40.0

_PRIORITY_LEVELS = {
    0: "CRITICAL",
    1: "CRITICAL",
    2: "CRITICAL",
    3: "ERROR",
    4: "WARNING",
    5: "INFO",
    6: "INFO",
    7: "DEBUG",
}


class JournalError(RuntimeError):
    """Structured failure while reading the local systemd journal."""

    def __init__(
        self,
        message,
        *,
        command=(),
        returncode=None,
        timeout=None,
        stdout="",
        stderr="",
    ):
        super().__init__(message)
        self.command = tuple(command)
        self.returncode = returncode
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr


def _diagnostic_text(value, *, limit=4000):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _systemd_sources(sources):
    selected = list(sources)
    for source in selected:
        if source.kind != "service":
            raise ValueError(
                f"journal reader requires concrete service sources: {source.identity}"
            )
        if source.backend != "systemd":
            raise ValueError(
                f"log source {source.identity!r} is not systemd-backed"
            )
        if not source.backend_id:
            raise ValueError(
                f"log source {source.identity!r} has no persisted backend identity"
            )
        if source.system is None:
            raise ValueError(
                f"log source {source.identity!r} has no journal scope"
            )
    return selected


def _build_command(
    sources,
    *,
    system,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
):
    """Build one safe journalctl invocation for one journal scope."""
    command = ["journalctl"]
    if not system:
        command.append("--user")
    command.extend(("--output=json", "--no-pager"))

    for source in sources:
        command.append(f"--unit={source.backend_id}")

    if since is not None:
        command.extend(("--since", str(since)))
    if until is not None:
        command.extend(("--until", str(until)))
    if limit is not None:
        limit = int(limit)
        if limit <= 0:
            raise ValueError("journal limit must be positive")
        command.append(f"--lines={limit}")
    if grep is not None:
        command.extend(("--grep", str(grep)))
    if reverse:
        command.append("--reverse")
    return command


def _timestamp(entry):
    raw = entry.get("__REALTIME_TIMESTAMP")
    if raw is None:
        raise ValueError("journal entry has no realtime timestamp")
    try:
        micros = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("journal entry has invalid realtime timestamp") from exc
    return datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc)


def _pid(entry):
    value = entry.get("_PID")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _priority(entry):
    value = entry.get("PRIORITY")
    if value in (None, ""):
        return None, None
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return None, value
    return _PRIORITY_LEVELS.get(priority), priority


def _entry_source(entry, sources):
    unit = entry.get("_SYSTEMD_UNIT") or entry.get("UNIT")
    if unit is not None:
        matches = [source for source in sources if source.backend_id == unit]
        if len(matches) == 1:
            return matches[0]

    if len(sources) == 1:
        return sources[0]

    raise ValueError(
        f"journal entry cannot be attributed to one requested source: unit={unit!r}"
    )


def _parse_entry(entry, sources):
    """Normalize one JSON journal entry into a backend-neutral LogRecord."""
    source = _entry_source(entry, sources)
    level, priority = _priority(entry)
    metadata = dict(entry)
    if priority is not None:
        metadata["journal_priority"] = priority

    message = entry.get("MESSAGE", "")
    if not isinstance(message, str):
        message = str(message)

    return LogRecord(
        timestamp=_timestamp(entry),
        source=source.identity,
        message=message,
        level=level,
        pid=_pid(entry),
        unit=entry.get("_SYSTEMD_UNIT") or entry.get("UNIT"),
        metadata=metadata,
    )


def _parse_output(output, sources):
    records = []
    for number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalError(
                f"invalid journal JSON on output line {number}"
            ) from exc
        if not isinstance(entry, dict):
            raise JournalError(
                f"invalid journal JSON object on output line {number}"
            )
        try:
            records.append(_parse_entry(entry, sources))
        except ValueError as exc:
            raise JournalError(
                f"invalid journal entry on output line {number}: {exc}"
            ) from exc
    return records


def _run(command, *, timeout):
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise JournalError(
            "journalctl is not available on this host",
            command=command,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = _diagnostic_text(exc.stdout)
        stderr = _diagnostic_text(exc.stderr)
        raise JournalError(
            f"journal query timed out after {exc.timeout}s",
            command=command,
            timeout=exc.timeout,
            stdout=stdout,
            stderr=stderr,
        ) from exc
    except subprocess.CalledProcessError as exc:
        stdout = _diagnostic_text(exc.stdout)
        stderr = _diagnostic_text(exc.stderr)
        message = f"journal query failed with exit {exc.returncode}"
        if stderr:
            message += f": {stderr}"
        elif stdout:
            message += f": {stdout}"
        raise JournalError(
            message,
            command=command,
            returncode=exc.returncode,
            stdout=stdout,
            stderr=stderr,
        ) from exc


def read_journal(
    sources,
    *,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
    timeout=JOURNALCTL_TIMEOUT,
):
    """Read concrete systemd log sources and return normalized records.

    Sources in the same user/system scope share one journalctl invocation.
    Mixed scopes require separate journalctl invocations and are merged by
    timestamp after normalization.
    """
    selected = _systemd_sources(sources)
    if not selected:
        return []

    groups = {
        system: [source for source in selected if source.system is system]
        for system in (False, True)
    }

    records = []
    for system, scoped_sources in groups.items():
        if not scoped_sources:
            continue
        command = _build_command(
            scoped_sources,
            system=system,
            since=since,
            until=until,
            limit=limit,
            grep=grep,
            reverse=reverse,
        )
        result = _run(command, timeout=timeout)
        records.extend(_parse_output(result.stdout, scoped_sources))

    records.sort(key=lambda record: record.timestamp, reverse=reverse)
    if limit is not None:
        records = records[: int(limit)]
    return records
