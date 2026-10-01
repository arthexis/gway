"""Bounded deterministic GitHub PR reconciliation.

Drive consumes normalized lifecycle status and applies only a small whitelist of
convergent, guarded mutations. Provider state remains authoritative; no Drive-
local lifecycle state is persisted.
"""

from __future__ import annotations

import json

from .status import Controller as StatusController


DRIVE_OUTCOMES = frozenset({"done", "waiting", "escalated", "changed"})
DEFAULT_MAX_ACTIONS = 8


class Controller(StatusController):
    """Reconcile one PR until policy reaches a deterministic boundary."""

    def drive(self, repository, pull, max_actions=DEFAULT_MAX_ACTIONS, mutate=True):
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
            changed = self._drive_changed(actions)
            if disposition == "done":
                return self._drive_result(
                    repository, pull, "changed" if changed else "done",
                    initial, current, actions,
                )
            if disposition == "wait":
                return self._drive_result(
                    repository, pull, "changed" if changed else "waiting",
                    initial, current, actions,
                )
            if disposition == "escalate":
                return self._drive_result(
                    repository, pull, "changed" if changed else "escalated",
                    initial, current, actions,
                )
            if disposition != "auto":
                return self._drive_result(
                    repository, pull, "changed" if changed else "escalated",
                    initial, current, actions,
                    reason="drive-unknown-disposition",
                )

            action = current.get("action")
            if not isinstance(action, dict) or not action.get("kind"):
                return self._drive_result(
                    repository, pull, "changed" if changed else "escalated",
                    initial, current, actions,
                    reason="drive-missing-action",
                )
            if len(actions) >= max_actions:
                return self._drive_result(
                    repository, pull, "changed" if changed else "escalated",
                    initial, current, actions,
                    reason="drive-action-budget-exhausted",
                    pending_action=action,
                )

            execution = self._execute_drive_action(
                repository, pull, action, mutate=mutate
            )
            if execution is None:
                return self._drive_result(
                    repository, pull, "changed" if changed else "escalated",
                    initial, current, actions,
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
                    "changed" if self._drive_changed(actions) else "escalated",
                    initial,
                    current,
                    actions,
                    reason="drive-no-progress",
                )

    def _drive_status(self, repository, pull):
        """Read one fresh normalized lifecycle status for Drive."""
        return self._status_pull(str(repository), int(pull))

    def _execute_drive_action(self, repository, pull, action, mutate=True):
        """Execute one whitelisted convergent Drive action."""
        kind = str(action.get("kind") or "")
        handlers = {
            "update-branch": self._drive_update_branch,
            "enable-auto-merge": self._drive_enable_auto_merge,
            "ensure-auto-merge": self._drive_enable_auto_merge,
            "merge-pull": self._drive_merge_pull,
        }
        handler = handlers.get(kind)
        if handler is None:
            return None
        if not mutate:
            raise PermissionError("GitHub Drive mutation is disabled")
        return handler(str(repository), int(pull), dict(action))

    def _drive_guarded_pull(self, repository, pull, action):
        expected = action.get("expected_head_sha")
        if expected is None or not str(expected).strip():
            raise ValueError("Drive action requires expected_head_sha")
        expected = str(expected)
        pr = self.pull(repository, pull)
        actual = ((pr or {}).get("head") or {}).get("sha")
        if not actual:
            raise ValueError("pull request response is missing head SHA")
        return pr, expected, str(actual)

    @staticmethod
    def _drive_stale_action(kind, expected, actual):
        return {
            "kind": kind,
            "result": "stale",
            "expected_head_sha": expected,
            "actual_head_sha": actual,
        }

    def _drive_update_branch(self, repository, pull, action):
        pr, expected, actual = self._drive_guarded_pull(repository, pull, action)
        del pr
        if actual != expected:
            return self._drive_stale_action("update-branch", expected, actual)
        response = self._github().request(
            "PUT",
            f"{self._repo(repository)}/pulls/{int(pull)}/update-branch",
            json={"expected_head_sha": expected},
        ).data
        return {
            "kind": "update-branch",
            "result": "changed",
            "expected_head_sha": expected,
            "provider": response,
        }

    def _drive_enable_auto_merge(self, repository, pull, action):
        pr, expected, actual = self._drive_guarded_pull(repository, pull, action)
        if actual != expected:
            return self._drive_stale_action("ensure-auto-merge", expected, actual)
        if pr.get("auto_merge") is not None:
            return {
                "kind": "ensure-auto-merge",
                "result": "already",
                "expected_head_sha": expected,
            }
        node_id = pr.get("node_id")
        if not node_id:
            raise ValueError("pull request response is missing node_id")
        merge_method = str(
            action.get("merge_method") or self._drive_merge_method(repository)
        ).upper()
        if merge_method not in {"MERGE", "SQUASH", "REBASE"}:
            raise ValueError("Drive auto-merge method must be merge, squash, or rebase")
        query = """
        mutation($id: ID!, $method: PullRequestMergeMethod!) {
          enablePullRequestAutoMerge(input: {
            pullRequestId: $id,
            mergeMethod: $method
          }) {
            pullRequest {
              id
              number
              autoMergeRequest { enabledAt mergeMethod }
            }
          }
        }
        """
        payload = self._github().graphql(
            query, {"id": node_id, "method": merge_method}
        ).data
        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
        return {
            "kind": "ensure-auto-merge",
            "result": "changed",
            "expected_head_sha": expected,
            "merge_method": merge_method.lower(),
            "provider": (
                (payload.get("data") or {})
                .get("enablePullRequestAutoMerge", {})
                .get("pullRequest")
            ),
        }

    def _drive_merge_method(self, repository):
        repo = self.repository(repository)
        if repo.get("allow_squash_merge"):
            return "SQUASH"
        if repo.get("allow_merge_commit"):
            return "MERGE"
        if repo.get("allow_rebase_merge"):
            return "REBASE"
        raise ValueError("repository does not allow a supported pull request merge method")

    def _drive_merge_pull(self, repository, pull, action):
        pr, expected, actual = self._drive_guarded_pull(repository, pull, action)
        if actual != expected:
            return self._drive_stale_action("merge-pull", expected, actual)
        if pr.get("merged"):
            return {
                "kind": "merge-pull",
                "result": "already",
                "expected_head_sha": expected,
            }
        provider = self.merge_pull(
            repository,
            pull,
            expected,
            method=action.get("merge_method"),
        )
        return {
            "kind": "merge-pull",
            "result": "changed",
            "expected_head_sha": expected,
            "provider": provider,
        }

    @staticmethod
    def _drive_changed(actions):
        """Return whether this invocation actually applied a provider mutation."""
        return any(action.get("result") == "changed" for action in actions)

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
        repository, pull, outcome, initial, final, actions, *,
        reason=None, pending_action=None,
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
