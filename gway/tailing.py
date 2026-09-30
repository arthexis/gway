"""Streaming observation support for long-running GWAY operations."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone

from .tokens import Token


_TERMINAL_GITHUB_STATES = {
    "completed",
    "success",
    "failure",
    "cancelled",
    "canceled",
    "skipped",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
}


def _stable(value):
    """Return a deterministic JSON-compatible representation for change detection."""
    if isinstance(value, Mapping):
        return {
            str(key): _stable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_stable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def _fingerprint(value):
    return json.dumps(
        _stable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _event(sequence, kind, operation, value, *, terminal=False):
    return {
        "sequence": sequence,
        "kind": kind,
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value": _stable(value),
        "terminal": bool(terminal),
    }


def _github_operation_words(operation):
    """Normalize accepted GitHub operation spellings for terminal detection."""
    words = str(operation).replace(".", " ").replace("_", " ").split()
    return tuple(word.casefold() for word in words)


def _github_terminal(operation, value):
    """Return whether a GitHub status operation reached its natural terminal state."""
    words = _github_operation_words(operation)
    if len(words) < 2 or words[0] != "github":
        return False
    subject = words[1]
    if subject not in {"check", "checks", "job", "jobs", "run", "runs"}:
        return False

    records = value if isinstance(value, list) else [value]
    if not records:
        return False
    for record in records:
        if not isinstance(record, Mapping):
            return False
        status = str(record.get("status") or "").casefold()
        conclusion = str(record.get("conclusion") or "").casefold()
        if (
            status not in _TERMINAL_GITHUB_STATES
            and conclusion not in _TERMINAL_GITHUB_STATES
        ):
            return False
    return True


def terminal(operation, value):
    """Return whether a known observable operation has naturally completed."""
    return _github_terminal(operation, value)


def iter_events(
    observe,
    operation,
    *,
    interval=2.0,
    timeout=None,
    changes=True,
    sleep=time.sleep,
    clock=time.monotonic,
):
    """Yield structured events while repeatedly observing one operation.

    Native iterators are forwarded item-by-item. Ordinary finite results are
    polled, with unchanged snapshots suppressed by default. Known operations
    such as GitHub checks/jobs/runs stop when their status becomes terminal.
    Other operations continue until cancellation or the optional timeout.
    """
    interval = float(interval)
    if interval < 0:
        raise ValueError("tail interval cannot be negative")
    if timeout is not None:
        timeout = float(timeout)
        if timeout < 0:
            raise ValueError("tail timeout cannot be negative")

    started = clock()
    sequence = 0
    previous = None
    observed = False

    while True:
        value = observe()

        if isinstance(value, Iterator):
            for item in value:
                sequence += 1
                yield _event(sequence, "update", operation, item)
            sequence += 1
            yield _event(sequence, "complete", operation, None, terminal=True)
            return

        fingerprint = _fingerprint(value)
        changed = not observed or fingerprint != previous
        done = terminal(operation, value)
        if changed or not changes:
            sequence += 1
            yield _event(
                sequence,
                "complete" if done else "update",
                operation,
                value,
                terminal=done,
            )
        elif done:
            sequence += 1
            yield _event(sequence, "complete", operation, value, terminal=True)

        if done:
            return

        observed = True
        previous = fingerprint
        if timeout is not None and clock() - started >= timeout:
            sequence += 1
            yield _event(sequence, "timeout", operation, value, terminal=True)
            return
        if interval:
            sleep(interval)


class Controller:
    """Expose tailing as a generic read-only execution operator."""

    def __init__(self, gateway):
        self.gateway = gateway

    def tail(
        self,
        *command: Token,
        interval: float = 2.0,
        timeout: float = None,
        changes: bool = True,
        mutate=False,
    ):
        """Stream changes from a command until completion or cancellation.

        Use tail -- <command> to make the wrapped command boundary explicit.
        The wrapped operation always executes with mutation disabled.
        """
        del mutate
        command = tuple(command)
        if command and str(command[0]) == "--":
            command = command[1:]
        if not command:
            raise TypeError("tail requires a command after --")

        target = (
            command[0]
            if len(command) == 1 and isinstance(command[0], str)
            else list(command)
        )
        operation = " ".join(map(str, command))

        def observe():
            value = self.gateway.execute(target, mutate=False)
            if not isinstance(value, Iterator):
                return value

            iterator = value

            def readonly_iterator():
                while True:
                    with self.gateway.mutation_scope(mutate=False):
                        with self.gateway.observational_state_scope():
                            try:
                                item = next(iterator)
                            except StopIteration:
                                return
                    yield item

            return readonly_iterator()

        return iter_events(
            observe,
            operation,
            interval=interval,
            timeout=timeout,
            changes=changes,
        )


def register(gateway):
    controller = Controller(gateway)
    gateway._tail_controller = controller
    gateway.tail = gateway.wrap("tail", controller.tail)
    return controller
