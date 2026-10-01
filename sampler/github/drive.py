"""Bounded deterministic GitHub PR reconciliation shell.

Chunk 1 defines Drive's reusable result contract and control flow without
executing production mutations. Later chunks provide the guarded action
dispatcher by overriding the action hook already exercised here.
"""

from __future__ import annotations

import json

from .status import Controller as StatusController


DRIVE_OUTCOMES = frozenset({"done", "waiting", "escalated", "changed"})
DEFAULT_MAX_ACTIONS = 8


class Controller(StatusController):
    """Reconcile one PR until policy reaches a deterministic boundary."""

    def drive(self, repository, pull, max_actions=DEFAULT_MAX_ACTIONS):
        """Run one bounded, resumable reconciliation pass for a pull request."""
        repository = str(repository)
        pull = int(pull)
        max_actions = int(max_actions)
        if max_actions < 1:
            raise ValueError("max_actions must be at least 1")

        initial = self._drive_status(repository, pull)
        current = initial
        actions = []

        while True:
            disposition = current.get("disposition")
            if disposition == "done":
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "done",
                    initial,
                    current,
                    actions,
                )
            if disposition == "wait":
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "waiting",
                    initial,
                    current,
                    actions,
                )
            if disposition == "escalate":
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "escalated",
                    initial,
                    current,
                    actions,
                )
            if disposition != "auto":
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "escalated",
                    initial,
                    current,
                    actions,
                    reason="drive-unknown-disposition",
                )

            action = current.get("action")
            if not isinstance(action, dict) or not action.get("kind"):
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "escalated",
                    initial,
                    current,
                    actions,
                    reason="drive-missing-action",
                )
            if len(actions) >= max_actions:
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "escalated",
                    initial,
                    current,
                    actions,
                    reason="drive-action-budget-exhausted",
                    pending_action=action,
                )

            execution = self._execute_drive_action(repository, pull, action)
            if execution is None:
                return self._drive_result(
                    repository,
                    pull,
                    "changed" if actions else "escalated",
                    initial,
                    current,
                    actions,
                    reason="drive-action-not-implemented",
                    pending_action=action,
                )

            actions.append(execution)
            previous_fingerprint = self._drive_fingerprint(current)
            current = self._drive_status(repository, pull)
            if self._drive_fingerprint(current) == previous_fingerprint:
                return self._drive_result(
                    repository,
                    pull,
                    "changed",
                    initial,
                    current,
                    actions,
                    reason="drive-no-progress",
                )

    def _drive_status(self, repository, pull):
        """Read one fresh normalized lifecycle status for Drive."""
        return self._status_pull(str(repository), int(pull))

    def _execute_drive_action(self, repository, pull, action):
        """Execute one known Drive action.

        Chunk 1 intentionally has no production action dispatcher. Returning
        ``None`` defines the action boundary that Chunk 2 will replace.
        """
        return None

    @staticmethod
    def _drive_fingerprint(status):
        """Return a stable fingerprint for no-progress detection."""
        relevant = {
            "status": status.get("status"),
            "disposition": status.get("disposition"),
            "action": status.get("action"),
            "diagnostic_target": status.get("diagnostic_target"),
        }
        return json.dumps(relevant, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _drive_result(
        repository,
        pull,
        outcome,
        initial,
        final,
        actions,
        *,
        reason=None,
        pending_action=None,
    ):
        if outcome not in DRIVE_OUTCOMES:
            raise ValueError(f"unsupported Drive outcome: {outcome}")
        result = {
            "repository": str(repository),
            "pr": int(pull),
            "outcome": outcome,
            "initial_status": initial.get("status"),
            "actions": list(actions),
            "final_status": final.get("status"),
            "disposition": final.get("disposition"),
        }
        diagnostic = final.get("diagnostic_target")
        if diagnostic is not None:
            result["diagnostic_target"] = diagnostic
        if reason is not None:
            result["reason"] = reason
        if pending_action is not None:
            result["pending_action"] = pending_action
        return result
