"""Background command execution helper for recipes."""

from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable, List, Tuple

__all__ = ["side"]


_FALSEY_STRINGS = {
    "",
    "0",
    "false",
    "f",
    "no",
    "n",
    "off",
    "none",
    "null",
    "nil",
    "undefined",
}


@dataclass
class _SideCommand:
    tokens: List[str]
    queues: Tuple[str, ...]
    id: int
    thread: threading.Thread | None = None


@dataclass
class _QueueState:
    name: str
    pending: Deque[_SideCommand] = field(default_factory=deque)
    current: _SideCommand | None = None


_DEFAULT_QUEUE = "__side_default__"
_SIDE_LOCK = threading.Lock()
_SIDE_QUEUES: dict[str, _QueueState] = {}
_PENDING_COMMANDS: list[_SideCommand] = []
_COMMAND_COUNTER = itertools.count(1)
_CONSOLE_TOOLS: dict[str, object] | None = None


def _coerce_when_to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _FALSEY_STRINGS:
            return False
        return bool(text)
    return bool(value)


def _get_console_tools() -> dict[str, object]:
    """Load helpers from :mod:`gway.console` lazily to avoid import cycles."""

    global _CONSOLE_TOOLS
    if _CONSOLE_TOOLS is None:
        from gway.console import join_unquoted_kwargs, load_recipe, normalize_token, process

        _CONSOLE_TOOLS = {
            "join_unquoted_kwargs": join_unquoted_kwargs,
            "load_recipe": load_recipe,
            "normalize_token": normalize_token,
            "process": process,
        }
    return _CONSOLE_TOOLS


def _ensure_queue(name: str) -> _QueueState:
    state = _SIDE_QUEUES.get(name)
    if state is None:
        state = _QueueState(name)
        _SIDE_QUEUES[name] = state
    return state


def _normalize_queue_names(tokens: Iterable[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        name = token.rstrip(":")
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _looks_like_command(tokens: List[str]) -> bool:
    if not tokens:
        return False

    tools = _get_console_tools()
    join = tools["join_unquoted_kwargs"]
    normalize = tools["normalize_token"]
    load_recipe = tools["load_recipe"]

    chunk = join(tokens)
    if not chunk:
        return False

    from gway import gw

    obj = gw
    remaining = list(chunk)
    path: list[str] = []

    while remaining:
        token = remaining[0]
        normalized = normalize(token)
        try:
            obj = getattr(obj, normalized)
            path.append(remaining.pop(0))
            continue
        except AttributeError:
            matched = False
            for size in range(len(remaining), 0, -1):
                joined = "_".join(normalize(part) for part in remaining[:size])
                try:
                    obj = getattr(obj, joined)
                    path.extend(remaining[:size])
                    remaining = remaining[size:]
                    matched = True
                    break
                except AttributeError:
                    continue
            if not matched:
                break

    if callable(obj) and path:
        return True

    try:
        load_recipe(chunk[0], strict=False)
        return True
    except FileNotFoundError:
        return False


def _find_command_start(tokens: List[str]) -> int | None:
    if not tokens:
        return None
    for index in range(len(tokens)):
        if _looks_like_command(tokens[index:]):
            return index
    return None


def _split_args(args: Tuple[str, ...]) -> tuple[list[str], list[str]]:
    tokens = list(args)
    if not tokens:
        return [], []

    queue_tokens: list[str] = []
    idx = 0
    while idx < len(tokens) and tokens[idx].endswith(":"):
        queue_tokens.append(tokens[idx][:-1])
        idx += 1

    remaining = tokens[idx:]
    start = _find_command_start(remaining)
    if start is None:
        queue_tokens.extend(remaining)
        return queue_tokens, []

    queue_tokens.extend(remaining[:start])
    command_tokens = remaining[start:]
    return queue_tokens, command_tokens


def _command_ready_locked(command: _SideCommand) -> bool:
    for name in command.queues:
        state = _SIDE_QUEUES[name]
        if state.current is not None:
            return False
        if not state.pending or state.pending[0] is not command:
            return False
    return True


def _collect_ready_locked() -> list[_SideCommand]:
    ready: list[_SideCommand] = []
    for command in list(_PENDING_COMMANDS):
        if _command_ready_locked(command):
            for name in command.queues:
                state = _SIDE_QUEUES[name]
                if state.pending and state.pending[0] is command:
                    state.pending.popleft()
                state.current = command
            _PENDING_COMMANDS.remove(command)
            ready.append(command)
    return ready


def _launch_command(command: _SideCommand) -> None:
    from gway import gw

    def runner() -> None:
        process = _get_console_tools()["process"]
        try:
            process([command.tokens])
        except SystemExit:
            pass
        except Exception as exc:  # pragma: no cover - defensive logging
            gw.exception(exc)
        finally:
            with _SIDE_LOCK:
                for name in command.queues:
                    state = _SIDE_QUEUES.get(name)
                    if state and state.current is command:
                        state.current = None
                ready_commands = _collect_ready_locked()
            for next_command in ready_commands:
                _launch_command(next_command)

    thread = threading.Thread(
        target=runner,
        name=f"gway-side-{command.id}",
        daemon=True,
    )
    command.thread = thread
    gw.debug(
        f"[side] starting command {command.id} -> {' '.join(command.tokens)} on {command.queues}"
    )
    gw._async_threads.append(thread)
    thread.start()


def side(*args: str, when: str | None = None) -> dict:
    """Schedule ``args`` to run in the background, optionally on named queues."""

    from gway import gw

    queue_tokens, command_tokens = _split_args(args)
    queue_names = _normalize_queue_names(queue_tokens)
    command_text = " ".join(command_tokens)

    if not queue_names:
        queue_names = [_DEFAULT_QUEUE]

    should_run = True
    original_when = when
    resolved_when = when

    if when is not None:
        if isinstance(when, str):
            try:
                resolved_when = gw.resolve(when)
            except Exception as exc:
                gw.debug(
                    f"[side] failed to resolve --when expression {when!r}: {exc}"
                )
                resolved_when = when
        try:
            should_run = gw.cast.to_bool(resolved_when)
        except Exception as exc:
            gw.debug(
                f"[side] failed to coerce --when value {resolved_when!r} to bool: {exc}"
            )
            should_run = _coerce_when_to_bool(resolved_when)

    if not should_run:
        detail = command_text if command_text else "queue initialization"
        gw.debug(
            f"[side] skipped {detail} on queues {queue_names} because --when={original_when!r} "
            f"resolved to {resolved_when!r}"
        )
        return {
            "queues": queue_names,
            "command": command_text or None,
            "status": "skipped",
            "when": original_when,
        }

    with _SIDE_LOCK:
        for name in queue_names:
            _ensure_queue(name)

    if not command_tokens:
        gw.debug(f"[side] initialized queue(s): {queue_names}")
        return {"queues": queue_names, "status": "ready"}

    command = _SideCommand(list(command_tokens), tuple(queue_names), next(_COMMAND_COUNTER))

    with _SIDE_LOCK:
        for name in queue_names:
            _SIDE_QUEUES[name].pending.append(command)
        _PENDING_COMMANDS.append(command)
        ready_commands = _collect_ready_locked()
        started_now = command in ready_commands

    for ready in ready_commands:
        _launch_command(ready)

    status = "started" if started_now else "queued"
    gw.debug(
        f"[side] {status} command {command.id} on queues {queue_names}: {command_text}"
    )

    return {
        "id": command.id,
        "queues": queue_names,
        "command": command_text,
        "status": status,
    }


def _reset_side_state_for_tests() -> None:
    """Reset internal queues (intended for unit tests)."""

    global _COMMAND_COUNTER, _CONSOLE_TOOLS
    with _SIDE_LOCK:
        _PENDING_COMMANDS.clear()
        _SIDE_QUEUES.clear()
    _COMMAND_COUNTER = itertools.count(1)
    _CONSOLE_TOOLS = None
