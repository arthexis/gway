"""Higher-level GitHub checks built from source-read primitives."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
import re
import zipfile

from .githubops import Controller as BaseController


_ARTIFACT_NAME = "gway-ci-result"
_DISPATCH_TITLE = re.compile(r"\bPR\s*#(?P<pull>\d+)\s*@\s*(?P<head>[0-9a-fA-F]{7,40})\b")
_STATE = {
    "success": "passed",
    "failure": "failed",
    "timed_out": "failed",
    "action_required": "failed",
    "startup_failure": "failed",
    "cancelled": "cancelled",
    "skipped": "skipped",
    "neutral": "neutral",
}


def _state(status, conclusion):
    if status in {"queued", "in_progress", "requested", "waiting", "pending"}:
        return "pending"
    return _STATE.get(conclusion, "unknown")


def _aggregate(states):
    states = list(states)
    if not states:
        return "pending"
    for value in ("failed", "pending", "cancelled"):
        if value in states:
            return value
    if all(value == "passed" for value in states):
        return "passed"
    if all(value in {"passed", "skipped", "neutral"} for value in states):
        return "neutral" if "neutral" in states else "skipped"
    return "unknown"


def _dispatch_target(run):
    if run.get("event") != "workflow_dispatch":
        return None
    match = _DISPATCH_TITLE.search(str(run.get("display_title") or ""))
    if match is None:
        return None
    return int(match.group("pull")), match.group("head").lower()


def _targets_head(run, *, pull, head):
    if str(run.get("head_sha") or "").lower() == head.lower():
        return True
    return _dispatch_target(run) == (int(pull), head.lower())


def _labels(pr):
    return [str(item.get("name")) for item in pr.get("labels", ()) if item.get("name")]


def _on_hold(pr):
    return any(label.lower() in {"on-hold", "on hold"} for label in _labels(pr))


class Controller(BaseController):
    """GitHub controller extended with compact normalized checks."""

    def _targets(self, repository, pulls, issue):
        targets = [int(pull) for pull in pulls]
        if issue is not None:
            if targets:
                raise ValueError("pull targets and --issue are mutually exclusive")
            targets = [
                int(item["number"])
                for item in self.issue_prs(repository, int(issue), state="open")
            ]
        if not targets:
            raise ValueError("at least one pull target or --issue is required")
        return targets

    def _run_check(self, operation, repository, pulls, *, issue=None, serial=False):
        targets = self._targets(repository, pulls, issue)
        if len(targets) == 1 and issue is None:
            return operation(repository, targets[0])
        if serial or len(targets) == 1:
            results = [operation(repository, pull) for pull in targets]
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(targets))) as executor:
                results = list(executor.map(lambda pull: operation(repository, pull), targets))
        result = {"repository": str(repository), "targets": targets, "pulls": results}
        if issue is not None:
            result["issue"] = int(issue)
        return result

    def check_pr(self, repository, *pulls, issue=None, serial=False):
        """Return compact intrinsic pull-request facts."""
        return self._run_check(self._check_pr_pull, repository, pulls, issue=issue, serial=serial)

    def _check_pr_pull(self, repository, pull):
        pr = self.pull(repository, pull)
        state = "merged" if pr.get("merged") else "closed" if pr.get("state") == "closed" else "draft" if pr.get("draft") else "ready"
        return {
            "repository": str(repository),
            "pr": int(pull),
            "state": state,
            "draft": bool(pr.get("draft")),
            "merged": bool(pr.get("merged")),
            "base": {"ref": (pr.get("base") or {}).get("ref"), "sha": (pr.get("base") or {}).get("sha")},
            "head": {"ref": (pr.get("head") or {}).get("ref"), "sha": (pr.get("head") or {}).get("sha")},
            "labels": _labels(pr),
            "on_hold": _on_hold(pr),
            "auto_merge": {"enabled": pr.get("auto_merge") is not None, "method": (pr.get("auto_merge") or {}).get("merge_method")},
            "url": pr.get("html_url"),
        }

    def check_reviews(self, repository, *pulls, issue=None, serial=False):
        """Return formal review requirements and unresolved-thread hygiene."""
        return self._run_check(self._check_reviews_pull, repository, pulls, issue=issue, serial=serial)

    def _check_reviews_pull(self, repository, pull):
        submitted = self.reviews(repository, pull)
        latest = {}
        for review in submitted:
            user = ((review.get("user") or {}).get("login"))
            if user:
                latest[user] = review
        approvals = [item for item in latest.values() if item.get("state") == "APPROVED"]
        changes = [item for item in latest.values() if item.get("state") == "CHANGES_REQUESTED"]
        decision = self.review_decision(repository, pull)
        unresolved = self.review_threads(repository, pull, unresolved=True)
        active = [thread for thread in unresolved if not thread.get("isOutdated")]
        if changes or decision == "CHANGES_REQUESTED":
            state = "changes-requested"
        elif decision == "REVIEW_REQUIRED":
            state = "review-required"
        elif unresolved:
            state = "unresolved"
        else:
            state = "clear"
        required = decision in {"APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}
        result = {
            "repository": str(repository),
            "pr": int(pull),
            "state": state,
            "approvals": len(approvals),
            "changes_requested": bool(changes or decision == "CHANGES_REQUESTED"),
            "requirements": {"decision": decision, "required": required, "satisfied": decision == "APPROVED" if required else True},
            "unresolved_threads": len(unresolved),
            "active_unresolved_threads": len(active),
            "unresolved_thread_ids": [thread.get("id") for thread in unresolved if thread.get("id")],
        }
        if unresolved or changes or decision == "REVIEW_REQUIRED":
            result["diagnostic_target"] = {"kind": "github-reviews", "pr": int(pull)}
        return result

    def check_freshness(self, repository, *pulls, issue=None, serial=False):
        """Return base/head freshness and deterministic updateability."""
        return self._run_check(self._check_freshness_pull, repository, pulls, issue=issue, serial=serial)

    def _check_freshness_pull(self, repository, pull):
        pr = self.pull(repository, pull)
        base = (pr.get("base") or {}).get("sha")
        head = (pr.get("head") or {}).get("sha")
        if pr.get("merged"):
            state, updatable = "merged", False
            compare = {}
        elif pr.get("state") == "closed":
            state, updatable = "closed", False
            compare = {}
        else:
            compare = self.compare(repository, base, head)
            behind = int(compare.get("behind_by") or 0)
            conflict = pr.get("mergeable") is False or pr.get("mergeable_state") == "dirty"
            if behind == 0:
                state, updatable = "up-to-date", False
            elif conflict:
                state, updatable = "conflict", False
            else:
                state, updatable = "behind", True
        result = {
            "repository": str(repository),
            "pr": int(pull),
            "state": state,
            "base_sha": base,
            "head_sha": head,
            "ahead_by": compare.get("ahead_by"),
            "behind_by": compare.get("behind_by"),
            "updatable": updatable,
        }
        if state == "behind":
            result["action"] = {"kind": "update-branch", "expected_head_sha": head}
        elif state == "conflict":
            result["diagnostic_target"] = {"kind": "github-merge", "pr": int(pull)}
        return result

    def check_merge(self, repository, *pulls, issue=None, serial=False):
        """Return mergeability and merge-authorization facts."""
        return self._run_check(self._check_merge_pull, repository, pulls, issue=issue, serial=serial)

    def _check_merge_pull(self, repository, pull):
        pr = self.pull(repository, pull)
        head = (pr.get("head") or {}).get("sha")
        auto = pr.get("auto_merge") is not None
        if pr.get("merged"):
            state, authorization, action = "merged", "complete", None
        elif pr.get("state") == "closed":
            state, authorization, action = "closed", "unavailable", None
        elif _on_hold(pr):
            state, authorization, action = "blocked", "on-hold", None
        elif pr.get("draft"):
            state, authorization, action = "blocked", "draft", None
        elif pr.get("mergeable") is None:
            state, authorization, action = "pending", "unknown", None
        elif pr.get("mergeable") is False:
            state = "conflict" if pr.get("mergeable_state") == "dirty" else "blocked"
            authorization, action = "unavailable", None
        elif auto:
            state, authorization, action = "ready", "native-auto-merge", None
        else:
            # GitHub rejects enabling auto-merge once the PR is already mergeable.
            # At that point the deterministic continuation is an expected-head merge.
            state, authorization = "ready", "direct-merge-required"
            action = {"kind": "merge-pull", "expected_head_sha": head}
        result = {
            "repository": str(repository),
            "pr": int(pull),
            "state": state,
            "head_sha": head,
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "authorization": {"state": authorization, "auto_merge_enabled": auto},
        }
        if action is not None:
            result["action"] = action
        if state in {"conflict", "blocked"}:
            result["diagnostic_target"] = {"kind": "github-merge", "pr": int(pull)}
        return result

    def artifacts(self, repository, run, name=None):
        params = {"per_page": 100}
        if name is not None:
            params["name"] = str(name)
        return self._all_enveloped(f"{self._repo(repository)}/actions/runs/{int(run)}/artifacts", "artifacts", params=params)

    def artifact_json(self, repository, artifact, filename="ci-result.json"):
        response = self._github().download_redirect(f"{self._repo(repository)}/actions/artifacts/{int(artifact)}/zip")
        payload = response.data
        if isinstance(payload, str):
            payload = payload.encode()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            try:
                content = archive.read(filename)
            except KeyError as exc:
                raise ValueError(f"artifact does not contain {filename}") from exc
        value = json.loads(content.decode("utf-8"))
        if not isinstance(value, dict):
            raise TypeError("canonical CI artifact must contain a JSON object")
        return value

    def check_ci(self, repository, *pulls, issue=None, serial=False):
        """Return normalized current-head CI facts for one or more PR targets."""
        return self._run_check(self._check_ci_pull, repository, pulls, issue=issue, serial=serial)

    def _check_ci_pull(self, repository, pull):
        root = self._repo(repository)
        pull = int(pull)
        pr = self.pull(repository, pull)
        head = ((pr or {}).get("head") or {}).get("sha")
        if not head:
            raise ValueError("pull request response is missing head SHA")

        direct = self._all_enveloped(f"{root}/actions/runs", "workflow_runs", params={"per_page": 100, "head_sha": head})
        dispatched = self._all_enveloped(f"{root}/actions/runs", "workflow_runs", params={"per_page": 100, "event": "workflow_dispatch"})
        by_id = {}
        for run in (*direct, *dispatched):
            if _targets_head(run, pull=pull, head=head):
                by_id[run.get("id")] = run
        current = [run for run_id, run in by_id.items() if run_id is not None]
        all_runs = self._all_enveloped(f"{root}/actions/runs", "workflow_runs", params={"per_page": 100, "event": "pull_request"})
        stale = [run for run in all_runs if run.get("head_branch") == ((pr.get("head") or {}).get("ref")) and run.get("head_sha") != head]

        workflows, artifact_errors, diagnostic = [], [], None
        for run in current:
            run_id = run.get("id")
            jobs = self.jobs(repository, run_id) if run_id is not None else []
            normalized_jobs = []
            for job in jobs:
                state = _state(job.get("status"), job.get("conclusion"))
                normalized_jobs.append({"id": job.get("id"), "name": job.get("name"), "state": state, "status": job.get("status"), "conclusion": job.get("conclusion"), "started_at": job.get("started_at"), "completed_at": job.get("completed_at"), "url": job.get("html_url")})
                if diagnostic is None and state == "failed":
                    diagnostic = {"kind": "github-ci", "run_id": run_id, "job_id": job.get("id")}
            artifact = canonical = None
            try:
                matches = self.artifacts(repository, run_id, name=_ARTIFACT_NAME) if run_id is not None else []
                if matches:
                    selected = max(matches, key=lambda item: item.get("id", 0))
                    artifact = {"name": _ARTIFACT_NAME, "available": True, "id": selected.get("id")}
                    canonical = self.artifact_json(repository, selected["id"])
                else:
                    artifact = {"name": _ARTIFACT_NAME, "available": False}
            except (ValueError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
                artifact = {"name": _ARTIFACT_NAME, "available": True, "valid": False}
                artifact_errors.append({"run_id": run_id, "error": str(exc)})
            workflows.append({"id": run_id, "name": run.get("name"), "state": _state(run.get("status"), run.get("conclusion")), "status": run.get("status"), "conclusion": run.get("conclusion"), "head_sha": run.get("head_sha"), "tested_head_sha": head, "current": True, "url": run.get("html_url"), "jobs": normalized_jobs, "artifact": artifact, "result": canonical})

        state = _aggregate(item["state"] for item in workflows)
        failure_kind = None
        artifact_result = next((item["result"] for item in workflows if item["result"] is not None), None)
        if state == "failed":
            failed = [item for item in workflows if item["state"] == "failed"]
            modeled = [item for item in failed if isinstance(item["result"], dict) and item["result"].get("state") == "failed"]
            if failed and len(modeled) == len(failed):
                failure_kind, artifact_result = "ci", modeled[0]["result"]
            else:
                failure_kind, artifact_result = "infrastructure", None
        result = {"repository": str(repository), "pr": pull, "head_sha": head, "state": state, "current": bool(current), "workflows": workflows, "stale_runs": len(stale), "result": artifact_result, "failure_kind": failure_kind, "diagnostic_target": diagnostic}
        if artifact_errors:
            result["artifact_errors"] = artifact_errors
        return result
