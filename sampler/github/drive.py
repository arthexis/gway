"""Bounded and streaming deterministic GitHub PR reconciliation.

Drive consumes normalized lifecycle status and applies only a small whitelist of
convergent, guarded mutations. Provider state remains authoritative; no Drive-
local lifecycle state is persisted.
"""

from __future__ import annotations

import json
import time

from .status import Controller as StatusController


DRIVE_OUTCOMES = frozenset({"done", "waiting", "escalated", "changed"})
DEFAULT_MAX_ACTIONS = 8
DEFAULT_STREAM_INTERVAL = 2.0


class Controller(StatusController):
    """Reconcile one PR until policy reaches a deterministic boundary."""

    def drive(
        self,
        repository,
        pull,
        max_actions=DEFAULT_MAX_ACTIONS,
        stream=False,
        interval=DEFAULT_STREAM_INTERVAL,
        timeout=None,
        mutate=True,
    ):
        """Reconcile a PR once, or stream reconciliation across wait states."""
        repository = str(repository)
        pull = int(pull)
        max_actions = int(max_actions)
        if max_actions < 1:
            raise ValueError("max_actions must be at least 1")
        if stream:
            return self._drive_stream(
                repository,
                pull,
                max_actions=max_actions,
                interval=interval,
                timeout=timeout,
                mutate=mutate,
            )
        return self._drive_once(
            repository,
            pull,
            max_actions=max_actions,
            mutate=mutate,
        )

    def _drive_once(
        self,
        repository,
        pull,
        *,
        max_actions=DEFAULT_MAX_ACTIONS,
        mutate=True,
        action_offset=0,
    ):
        """Run one bounded, resumable reconciliation pass."""
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
            if action_offset + len(actions) >= max_actions:
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

    def _drive_stream(
        self,
        repository,
        pull,
        *,
        max_actions=DEFAULT_MAX_ACTIONS,
        interval=DEFAULT_STREAM_INTERVAL,
        timeout=None,
        mutate=True,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        """Yield structured Drive events while continuing across wait states."""
        interval = float(interval)
        if interval < 0:
            raise ValueError("Drive stream interval cannot be negative")
        if timeout is not None:
            timeout = float(timeout)
            if timeout < 0:
                raise ValueError("Drive stream timeout cannot be negative")

        def events():
            started = clock()
            sequence = 0
            action_count = 0
            changed = False
            last_status = None
            last_fingerprint = None

            def emit(event, **value):
                nonlocal sequence
                sequence += 1
                return {
                    "sequence": sequence,
                    "event": event,
                    "repository": repository,
                    "pr": pull,
                    **value,
                }

            while True:
                result = self._drive_once(
                    repository,
                    pull,
                    max_actions=max_actions,
                    mutate=mutate,
                    action_offset=action_count,
                )
                for action in result.get("actions", []):
                    action_count += 1
                    changed = changed or action.get("result") == "changed"
                    yield emit("action", action=action)

                boundary = self._drive_status(repository, pull)
                fingerprint = self._drive_fingerprint(boundary)
                status = boundary.get("status")
                disposition = boundary.get("disposition")
                if last_status is not None and fingerprint != last_fingerprint:
                    yield emit("transition", before=last_status, after=status)
                if fingerprint != last_fingerprint:
                    yield emit(
                        "status",
                        status=status,
                        disposition=disposition,
                        diagnostic_target=boundary.get("diagnostic_target"),
                    )
                last_status = status
                last_fingerprint = fingerprint

                reason = result.get("reason")
                if reason is not None:
                    yield emit(
                        "terminal",
                        outcome="escalated",
                        status=status,
                        disposition=disposition,
                        reason=reason,
                        changed=changed,
                        pending_action=result.get("pending_action"),
                        diagnostic_target=boundary.get("diagnostic_target"),
                        terminal=True,
                    )
                    return
                if disposition == "done":
                    yield emit(
                        "terminal",
                        outcome="done",
                        status=status,
                        disposition=disposition,
                        changed=changed,
                        terminal=True,
                    )
                    return
                if disposition == "escalate":
                    yield emit(
                        "terminal",
                        outcome="escalated",
                        status=status,
                        disposition=disposition,
                        changed=changed,
                        diagnostic_target=boundary.get("diagnostic_target"),
                        terminal=True,
                    )
                    return
                if disposition != "wait":
                    continue

                while True:
                    if timeout is not None and clock() - started >= timeout:
                        yield emit(
                            "timeout",
                            status=last_status,
                            disposition="wait",
                            changed=changed,
                            terminal=True,
                        )
                        return
                    if interval:
                        sleep(interval)
                    current = self._drive_status(repository, pull)
                    current_fingerprint = self._drive_fingerprint(current)
                    if current_fingerprint == last_fingerprint:
                        continue
                    current_status = current.get("status")
                    yield emit(
                        "transition",
                        before=last_status,
                        after=current_status,
                    )
                    yield emit(
                        "status",
                        status=current_status,
                        disposition=current.get("disposition"),
                        diagnostic_target=current.get("diagnostic_target"),
                    )
                    last_status = current_status
                    last_fingerprint = current_fingerprint
                    break

        return events()

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
            "disable-auto-merge": self._drive_disable_auto_merge,
            "ensure-auto-merge-disabled": self._drive_disable_auto_merge,
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

    def _drive_disable_auto_merge(self, repository, pull, action):
        pr, expected, actual = self._drive_guarded_pull(repository, pull, action)
        if actual != expected:
            return self._drive_stale_action(
                "ensure-auto-merge-disabled", expected, actual
            )
        if pr.get("auto_merge") is None:
            return {
                "kind": "ensure-auto-merge-disabled",
                "result": "already",
                "expected_head_sha": expected,
            }
        node_id = pr.get("node_id")
        if not node_id:
            raise ValueError("pull request response is missing node_id")
        query = """
        mutation($id: ID!) {
          disablePullRequestAutoMerge(input: {pullRequestId: $id}) {
            pullRequest {
              id
              number
              autoMergeRequest { enabledAt mergeMethod }
            }
          }
        }
        """
        payload = self._github().graphql(query, {"id": node_id}).data
        if payload.get("errors"):
            raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
        return {
            "kind": "ensure-auto-merge-disabled",
            "result": "changed",
            "expected_head_sha": expected,
            "provider": (
                (payload.get("data") or {})
                .get("disablePullRequestAutoMerge", {})
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
