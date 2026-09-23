"""Bounded journald reads for concrete GWAY log sources."""

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


def _concrete_sources(sources):
    selected = list(sources)
    for source in selected:
        if source.kind == "project":
            raise ValueError(
                f"journal reader requires concrete sources: {source.identity}"
            )
        if source.backend not in {"systemd", "journal"}:
            raise ValueError(
                f"log source {source.identity!r} is not journal-readable"
            )
        if not source.backend_id:
            raise ValueError(
                f"log source {source.identity!r} has no persisted backend identity"
            )
        if source.backend == "systemd":
            if source.kind != "service":
                raise ValueError(
                    f"systemd log source must be a service: {source.identity}"
                )
            if source.system is None:
                raise ValueError(
                    f"log source {source.identity!r} has no journal scope"
                )
    return selected


def _build_command(
    sources,
    *,
    backend,
    system=None,
    since=None,
    until=None,
    limit=None,
    grep=None,
    reverse=False,
):
    """Build one safe journalctl invocation for one journal scope."""
    command = ["journalctl"]
    if backend == "systemd" and not system:
        command.append("--user")
    command.extend(("--output=json", "--no-pager"))

    if backend == "systemd":
        unit_option = "--unit" if system else "--user-unit"
        for source in sources:
            command.append(f"{unit_option}={source.backend_id}")
    elif backend == "journal":
        for source in sources:
            command.append(f"SYSLOG_IDENTIFIER={source.backend_id}")
    else:
        raise ValueError(f"Unsupported journal backend: {backend}")

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
    identifier = entry.get("SYSLOG_IDENTIFIER")
    if identifier is not None:
        matches = [
            source
            for source in sources
            if source.backend == "journal" and source.backend_id == identifier
        ]
        if len(matches) == 1:
            return matches[0]

    unit = (
        entry.get("_SYSTEMD_UNIT")
        or entry.get("_SYSTEMD_USER_UNIT")
        or entry.get("UNIT")
    )
    if unit is not None:
        matches = [
            source
            for source in sources
            if source.backend == "systemd" and source.backend_id == unit
        ]
        if len(matches) == 1:
            return matches[0]

    if len(sources) == 1:
        return sources[0]

    raise ValueError(
        "journal entry cannot be attributed to one requested source: "
        f"identifier={identifier!r} unit={unit!r}"
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
        unit=(
            entry.get("_SYSTEMD_UNIT")
            or entry.get("_SYSTEMD_USER_UNIT")
            or entry.get("UNIT")
        ),
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
        if (
            exc.returncode == 1
            and "--grep" in command
            and not stdout
            and not stderr
        ):
            return subprocess.CompletedProcess(
                command,
                exc.returncode,
                stdout="",
                stderr="",
            )
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
    """Read concrete journal-readable sources and return normalized records.

    Systemd sources share one query per user/system scope. Direct journal
    identifier sources share one SYSLOG_IDENTIFIER query. Results from the
    required native queries are merged by timestamp after normalization.
    """
    selected = _concrete_sources(sources)
    if not selected:
        return []

    groups = [
        (
            "systemd",
            False,
            [
                source
                for source in selected
                if source.backend == "systemd" and source.system is False
            ],
        ),
        (
            "systemd",
            True,
            [
                source
                for source in selected
                if source.backend == "systemd" and source.system is True
            ],
        ),
        (
            "journal",
            None,
            [source for source in selected if source.backend == "journal"],
        ),
    ]

    records = []
    for backend, system, scoped_sources in groups:
        if not scoped_sources:
            continue
        command = _build_command(
            scoped_sources,
            backend=backend,
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
