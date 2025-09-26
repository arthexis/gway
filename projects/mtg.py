"""Magic: The Gathering Arena log helpers."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

__all__ = ["scan_logs", "candidate_log_paths"]

_LOG_LINE = re.compile(
    r"^\[(?P<context>[^\]]+)\](?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+): (?P<message>.*)$"
)

_DIRECTION = re.compile(
    r"^(?P<actor>[^-<]+?)\s*(?P<arrow><-|->)\s*(?P<target>[^:]+?)(?::\s*(?P<event>.*))?$"
)


def candidate_log_paths() -> Iterator[Path]:
    """Yield likely locations for the Arena ``Player.log`` file.

    The function emits paths in priority order, taking into account common
    defaults for Windows, macOS, and Linux installations. Environment
    variables such as ``MTGA_LOG_PATH`` and ``MTGA_LOG_DIR`` are honoured when
    present.
    """

    env_path = os.environ.get("MTGA_LOG_PATH")
    if env_path:
        yield Path(env_path).expanduser()

    env_dir = os.environ.get("MTGA_LOG_DIR")
    if env_dir:
        yield Path(env_dir).expanduser() / "Player.log"

    home = Path.home()
    windows_path = home / "AppData" / "LocalLow" / "Wizards Of The Coast" / "MTGA" / "Player.log"
    mac_path = home / "Library" / "Logs" / "Wizards Of The Coast" / "MTGA" / "Player.log"
    linux_path = home / "Documents" / "MTGA" / "Player.log"

    for path in (windows_path, mac_path, linux_path):
        yield path


def scan_logs(
    *,
    source: str | os.PathLike[str] | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Parse an MTG Arena log into structured events.

    Parameters
    ----------
    source:
        Optional path to a ``Player.log`` file or directory. When omitted, the
        function attempts to locate the log using :func:`candidate_log_paths`.
    limit:
        When provided, restrict the returned entries to the most recent ``limit``
        events. ``None`` returns all parsed entries.

    Returns
    -------
    dict
        A dictionary containing the resolved path, parsed entries, and summary
        statistics suitable for CLI consumption.
    """

    log_path = _resolve_log_path(source)
    entries: list[dict[str, object]] = []
    pending_entry: dict[str, object] | None = None
    json_buffer: list[str] = []
    brace_depth = 0
    total_lines = 0

    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for total_lines, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if pending_entry is not None:
                json_buffer.append(line)
                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0:
                    payload_text = "\n".join(json_buffer)
                    payload, error = _parse_json(payload_text)
                    if payload is not None:
                        pending_entry["payload"] = payload
                    else:
                        pending_entry["payload_error"] = error
                        pending_entry["payload_text"] = payload_text
                    entries.append(pending_entry)
                    pending_entry = None
                    json_buffer.clear()
                continue

            if not line.strip():
                continue

            match = _LOG_LINE.match(line)
            if not match:
                entries.append({"line": total_lines, "raw": line})
                continue

            message = match.group("message")
            prefix, payload_snippet = _split_payload(message)

            entry: dict[str, object] = {
                "line": total_lines,
                "timestamp": match.group("timestamp"),
                "context": match.group("context"),
            }

            _apply_prefix_metadata(entry, prefix)

            if payload_snippet is not None:
                brace_depth = payload_snippet.count("{") - payload_snippet.count("}")
                json_buffer = [payload_snippet]
                if brace_depth <= 0:
                    payload_text = payload_snippet
                    payload, error = _parse_json(payload_text)
                    if payload is not None:
                        entry["payload"] = payload
                    else:
                        entry["payload_error"] = error
                        entry["payload_text"] = payload_text
                    entries.append(entry)
                    json_buffer.clear()
                    pending_entry = None
                else:
                    pending_entry = entry
                continue

            if "message" not in entry:
                entry["message"] = prefix.strip()

            entries.append(entry)

    if pending_entry is not None and json_buffer:
        payload_text = "\n".join(json_buffer)
        payload, error = _parse_json(payload_text)
        if payload is not None:
            pending_entry["payload"] = payload
        else:
            pending_entry["payload_error"] = error
            pending_entry["payload_text"] = payload_text
        entries.append(pending_entry)

    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        entries = entries[-limit:]

    stats = _summarise_entries(entries)
    stats["lines_processed"] = total_lines

    return {
        "path": str(log_path),
        "entries": entries,
        "stats": stats,
    }


def _summarise_entries(entries: Iterable[dict[str, object]]) -> dict[str, object]:
    events = Counter()
    json_count = 0
    parse_errors: list[dict[str, object]] = []

    for entry in entries:
        event = entry.get("event")
        if isinstance(event, str):
            events[event] += 1
        if "payload" in entry:
            json_count += 1
        if "payload_error" in entry:
            parse_errors.append({
                "line": entry.get("line"),
                "error": entry["payload_error"],
            })

    stats: dict[str, object] = {
        "total_entries": len(entries),
        "json_entries": json_count,
        "text_entries": len(entries) - json_count,
    }

    if events:
        stats["events"] = dict(events)
    if parse_errors:
        stats["parse_errors"] = parse_errors

    return stats


def _resolve_log_path(source: str | os.PathLike[str] | None) -> Path:
    if source is not None:
        source_path = Path(source).expanduser()
        if source_path.is_dir():
            source_path = source_path / "Player.log"
        if not source_path.is_file():
            raise FileNotFoundError(f"No MTG Arena log found at {source_path}")
        return source_path

    for candidate in candidate_log_paths():
        if candidate.is_file():
            return candidate

    raise FileNotFoundError("Unable to locate MTG Arena Player.log")


def _split_payload(message: str) -> tuple[str, str | None]:
    index = message.find("{")
    if index == -1:
        return message, None
    prefix = message[:index].rstrip()
    payload = message[index:]
    return prefix, payload


def _apply_prefix_metadata(entry: dict[str, object], prefix: str) -> None:
    match = _DIRECTION.match(prefix)
    if match:
        arrow = match.group("arrow")
        entry["actor"] = match.group("actor").strip()
        entry["target"] = match.group("target").strip()
        entry["direction"] = "outbound" if arrow == "->" else "inbound"
        event = match.group("event")
        if event:
            entry["event"] = event.strip()
    else:
        cleaned = prefix.strip()
        if cleaned:
            entry["message"] = cleaned


def _parse_json(text: str) -> tuple[dict[str, object] | list[object] | None, str | None]:
    snippet = text.strip().rstrip(",")
    try:
        return json.loads(snippet), None
    except json.JSONDecodeError as exc:
        return None, f"JSON decode error: {exc}"
