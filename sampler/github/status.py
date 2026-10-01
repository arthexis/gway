"""Deterministic PR status/disposition composition for Drive Phase 1."""

from __future__ import annotations

from .rollout import Controller as RolloutController


class Controller(RolloutController):
    """Compose compact checks into one read-only lifecycle decision."""

    def status(self, repository, *pulls, issue=None, serial=False):
        """Return repository status or one normalized lifecycle status per PR.

        With no PR/issue target this preserves the historical ``github status``
        repository summary. Supplying PR targets or ``--issue`` selects the Drive
        Phase 1 lifecycle classifier.
        """
        if not pulls and issue is None:
            return super().status(repository)
        return self._run_rollout(
            self._status_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    @staticmethod
    def _result(repository, pull, status, disposition, *, action=None, diagnostic=None):
        result = {
            "repository": str(repository),
            "pr": int(pull),
            "status": status,
            "disposition": disposition,
        }
        if action is not None:
            result["action"] = action
        if diagnostic is not None:
            result["diagnostic_target"] = diagnostic
        return result

    def _status_pull(self, repository, pull):
        repository = str(repository)
        pull = int(pull)

        # Rollout is the lifecycle gate. Once a pull is merged there is no value
        # in re-reading pre-merge CI/review/freshness state.
        rollout = self._check_rollout_pull(repository, pull)
        rollout_state = rollout.get("state")
        watchtower = rollout.get("watchtower") or {}

        if rollout_state == "certified":
            return self._result(repository, pull, "certified", "done")
        if rollout_state == "merged-not-main":
            return self._result(
                repository,
                pull,
                "merged-not-main",
                "wait",
                diagnostic=rollout.get("diagnostic_target"),
            )
        if rollout_state == "on-main":
            if watchtower.get("available"):
                return self._result(
                    repository,
                    pull,
                    "certification-pending",
                    "wait",
                    diagnostic=rollout.get("diagnostic_target"),
                )
            return self._result(repository, pull, "on-main", "done")
        if rollout_state == "closed":
            return self._result(
                repository,
                pull,
                "closed-without-merge",
                "escalate",
                diagnostic={"kind": "github-pr", "pr": pull},
            )

        pr = self._check_pr_pull(repository, pull)
        if pr.get("on_hold"):
            return self._result(repository, pull, "on-hold", "wait")
        if pr.get("state") == "draft":
            return self._result(repository, pull, "draft", "wait")

        reviews = self._check_reviews_pull(repository, pull)
        review_state = reviews.get("state")
        if review_state == "changes-requested":
            return self._result(
                repository,
                pull,
                "review-changes-requested",
                "escalate",
                diagnostic=reviews.get("diagnostic_target"),
            )
        if review_state == "review-required":
            return self._result(
                repository,
                pull,
                "review-required",
                "escalate",
                diagnostic=reviews.get("diagnostic_target"),
            )
        if review_state == "unresolved":
            # Unresolved does not itself prove a thread is mechanical/stale. Keep
            # the evidence boundary conservative until a future deterministic
            # rule can prove that automatic resolution is safe.
            return self._result(
                repository,
                pull,
                "review-threads-unresolved",
                "escalate",
                diagnostic=reviews.get("diagnostic_target"),
            )

        freshness = self._check_freshness_pull(repository, pull)
        freshness_state = freshness.get("state")
        if freshness_state == "conflict":
            return self._result(
                repository,
                pull,
                "merge-conflict",
                "escalate",
                diagnostic=freshness.get("diagnostic_target"),
            )
        if freshness_state == "behind":
            return self._result(
                repository,
                pull,
                "branch-behind",
                "auto",
                action=freshness.get("action"),
            )

        ci = self._check_ci_pull(repository, pull)
        ci_state = ci.get("state")
        if ci_state == "failed":
            return self._result(
                repository,
                pull,
                "ci-failed",
                "escalate",
                diagnostic=ci.get("diagnostic_target"),
            )
        if ci_state in {"pending", "unknown"}:
            return self._result(
                repository,
                pull,
                "ci-pending",
                "wait",
                diagnostic=ci.get("diagnostic_target"),
            )
        if ci_state == "cancelled":
            return self._result(
                repository,
                pull,
                "ci-cancelled",
                "escalate",
                diagnostic=ci.get("diagnostic_target"),
            )

        merge = self._check_merge_pull(repository, pull)
        merge_state = merge.get("state")
        action = merge.get("action")
        authorization = (merge.get("authorization") or {}).get("state")

        if merge_state == "conflict":
            return self._result(
                repository,
                pull,
                "merge-conflict",
                "escalate",
                diagnostic=merge.get("diagnostic_target"),
            )
        if action is not None:
            kind = action.get("kind")
            status = {
                "enable-auto-merge": "merge-awaiting-authorization",
                "merge-pull": "merge-ready",
            }.get(kind, "action-required")
            return self._result(
                repository,
                pull,
                status,
                "auto",
                action=action,
            )
        if merge_state == "pending":
            return self._result(
                repository,
                pull,
                "mergeability-pending",
                "wait",
                diagnostic=merge.get("diagnostic_target"),
            )
        if authorization == "native-auto-merge":
            return self._result(repository, pull, "merge-pending", "wait")
        if merge_state == "blocked":
            return self._result(
                repository,
                pull,
                "merge-blocked",
                "escalate",
                diagnostic=merge.get("diagnostic_target"),
            )

        # A state not covered by the normalized contracts is evidence that the
        # classifier needs extending; never silently invent an automatic action.
        return self._result(
            repository,
            pull,
            "unknown",
            "escalate",
            diagnostic={"kind": "github-pr", "pr": pull},
        )
