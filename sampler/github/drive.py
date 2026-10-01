"""Bounded deterministic GitHub PR reconciliation shell.

Chunk 1 defines Drive's reusable result contract and control flow without
executing mutations. Later chunks provide the guarded action dispatcher.
"""

from __future__ import annotations

from .status import Controller as StatusController


DRIVE_OUTCOMES = frozenset({"done", "waiting", "escalated", "changed"})
DEFAULT_MAX_ACTIONS = 8


class Controller(StatusController):
    """Reconcile one PR until policy reaches a deterministic boundary."""

    def drive(self, repository, pull, max_actions=DEFAULT_MAX_ACTIONS):
        """Return a bounded reconciliation result for one pull request.

        Chunk 1 intentionally performs no mutations. States with an ``auto``
        disposition therefore stop at the action boundary with a structured
        escalation. Rerunning the same command always reconstructs state from
        GitHub rather than relying on persisted Drive-local state.
        """
        repository = str(repository)
        pull = int(pull)
        max_actions = int(max_actions)
        if max_actions < 1:
            raise ValueError("max_actions must be at least 1")

        initial = self._drive_status(repository, pull)
        disposition = initial.get("disposition")

        if disposition == "done":
            return self._drive_result(
                repository, pull, "done", initial, initial, ()
            )
        if disposition == "wait":
            return self._drive_result(
                repository, pull, "waiting", initial, initial, ()
            )
        if disposition == "escalate":
            return self._drive_result(
                repository, pull, "escalated", initial, initial, ()
            )
        if disposition == "auto":
            return self._drive_result(
                repository,
                pull,
                "escalated",
                initial,
                initial,
                (),
                reason="drive-action-not-implemented",
                pending_action=initial.get("action"),
            )

        return self._drive_result(
            repository,
            pull,
            "escalated",
            initial,
            initial,
            (),
            reason="drive-unknown-disposition",
        )

    def _drive_status(self, repository, pull):
        """Read one fresh normalized lifecycle status for Drive."""
        return self._status_pull(str(repository), int(pull))

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
