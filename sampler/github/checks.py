"""Higher-level GitHub CI checks built from existing source-read primitives."""

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
    """Return ``(pull, head)`` encoded by a label-dispatched workflow run."""
    if run.get("event") != "workflow_dispatch":
        return None
    match = _DISPATCH_TITLE.search(str(run.get("display_title") or ""))
    if match is None:
        return None
    return int(match.group("pull")), match.group("head").lower()


def _targets_head(run, *, pull, head):
    if str(run.get("head_sha") or "").lower() == head.lower():
        return True
    target = _dispatch_target(run)
    return target == (int(pull), head.lower())


class Controller(BaseController):
    """GitHub controller extended with compact normalized CI checks."""

    def artifacts(self, repository, run, name=None):
        """List Actions artifacts for one workflow run."""
        params = {"per_page": 100}
        if name is not None:
            params["name"] = str(name)
        return self._all_enveloped(
            f"{self._repo(repository)}/actions/runs/{int(run)}/artifacts",
            "artifacts",
            params=params,
        )

    def artifact_json(self, repository, artifact, filename="ci-result.json"):
        """Download one ZIP artifact and decode a JSON member."""
        response = self._github().download_redirect(
            f"{self._repo(repository)}/actions/artifacts/{int(artifact)}/zip"
        )
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
        """Return normalized current-head CI facts for one or more PR targets.

        Explicit PR targets and ``--issue`` are mutually exclusive. Issue mode
        resolves its targets through ``github issue prs`` so later checks/status
        can share the same provider-backed relationship rule.
        """
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

        if len(targets) == 1 and issue is None:
            return self._check_ci_pull(repository, targets[0])

        if serial or len(targets) == 1:
            results = [self._check_ci_pull(repository, pull) for pull in targets]
        else:
            workers = min(8, len(targets))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(
                    executor.map(
                        lambda pull: self._check_ci_pull(repository, pull),
                        targets,
                    )
                )

        result = {
            "repository": str(repository),
            "targets": targets,
            "pulls": results,
        }
        if issue is not None:
            result["issue"] = int(issue)
        return result

    def _check_ci_pull(self, repository, pull):
        root = self._repo(repository)
        pull = int(pull)
        pr = self._github().request("GET", f"{root}/pulls/{pull}").data
        head = ((pr or {}).get("head") or {}).get("sha")
        if not head:
            raise ValueError("pull request response is missing head SHA")

        direct = self._all_enveloped(
            f"{root}/actions/runs",
            "workflow_runs",
            params={"per_page": 100, "head_sha": head},
        )
        dispatched = self._all_enveloped(
            f"{root}/actions/runs",
            "workflow_runs",
            params={"per_page": 100, "event": "workflow_dispatch"},
        )
        by_id = {}
        for run in (*direct, *dispatched):
            if _targets_head(run, pull=pull, head=head):
                by_id[run.get("id")] = run
        current = [run for run_id, run in by_id.items() if run_id is not None]

        all_runs = self._all_enveloped(
            f"{root}/actions/runs",
            "workflow_runs",
            params={"per_page": 100, "event": "pull_request"},
        )
        stale = [
            run
            for run in all_runs
            if run.get("head_branch") == ((pr.get("head") or {}).get("ref"))
            and run.get("head_sha") != head
        ]

        workflows = []
        artifact_errors = []
        diagnostic = None
        for run in current:
            run_id = run.get("id")
            jobs = self.jobs(repository, run_id) if run_id is not None else []
            normalized_jobs = []
            for job in jobs:
                state = _state(job.get("status"), job.get("conclusion"))
                normalized_jobs.append(
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "state": state,
                        "status": job.get("status"),
                        "conclusion": job.get("conclusion"),
                        "started_at": job.get("started_at"),
                        "completed_at": job.get("completed_at"),
                        "url": job.get("html_url"),
                    }
                )
                if diagnostic is None and state == "failed":
                    diagnostic = {
                        "kind": "github-ci",
                        "run_id": run_id,
                        "job_id": job.get("id"),
                    }

            artifact = None
            canonical = None
            try:
                matches = (
                    self.artifacts(repository, run_id, name=_ARTIFACT_NAME)
                    if run_id is not None
                    else []
                )
                if matches:
                    selected = max(matches, key=lambda item: item.get("id", 0))
                    artifact = {
                        "name": _ARTIFACT_NAME,
                        "available": True,
                        "id": selected.get("id"),
                    }
                    canonical = self.artifact_json(repository, selected["id"])
                else:
                    artifact = {"name": _ARTIFACT_NAME, "available": False}
            except (ValueError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
                artifact = {"name": _ARTIFACT_NAME, "available": True, "valid": False}
                artifact_errors.append({"run_id": run_id, "error": str(exc)})

            workflows.append(
                {
                    "id": run_id,
                    "name": run.get("name"),
                    "state": _state(run.get("status"), run.get("conclusion")),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "head_sha": run.get("head_sha"),
                    "tested_head_sha": head,
                    "current": True,
                    "url": run.get("html_url"),
                    "jobs": normalized_jobs,
                    "artifact": artifact,
                    "result": canonical,
                }
            )

        state = _aggregate(item["state"] for item in workflows)
        failure_kind = None
        artifact_result = next(
            (item["result"] for item in workflows if item["result"] is not None),
            None,
        )
        if state == "failed":
            failed = [item for item in workflows if item["state"] == "failed"]
            modeled = [
                item
                for item in failed
                if isinstance(item["result"], dict)
                and item["result"].get("state") == "failed"
            ]
            if failed and len(modeled) == len(failed):
                failure_kind = "ci"
                artifact_result = modeled[0]["result"]
            else:
                failure_kind = "infrastructure"
                artifact_result = None

        result = {
            "repository": str(repository),
            "pr": pull,
            "head_sha": head,
            "state": state,
            "current": bool(current),
            "workflows": workflows,
            "stale_runs": len(stale),
            "result": artifact_result,
            "failure_kind": failure_kind,
            "diagnostic_target": diagnostic,
        }
        if artifact_errors:
            result["artifact_errors"] = artifact_errors
        return result