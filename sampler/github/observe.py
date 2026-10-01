"""Rich GitHub evidence built on compact check and provider primitives."""

from __future__ import annotations

import json
import zipfile

from .checks import Controller as CheckController


_LOG_MODES = {"failed", "all", "none"}


def _log_text(log):
    if not isinstance(log, dict):
        return log
    value = log.get("content")
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return {
        "status": log.get("status"),
        "content_type": log.get("content_type"),
        "content": value,
    }


def _want_log(job, mode):
    if mode == "all":
        return True
    if mode == "none":
        return False
    return job.get("conclusion") in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
    }


class Controller(CheckController):
    """GitHub controller extended with rich read-only observation surfaces."""

    @staticmethod
    def _log_mode(logs):
        mode = str(logs).lower()
        if mode not in _LOG_MODES:
            raise ValueError("logs must be failed, all, or none")
        return mode

    def observe_pr(self, repository, *pulls, issue=None, serial=False):
        """Expand compact PR facts into full pull-request provider evidence."""
        return self._run_check(
            self._observe_pr_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_pr_pull(self, repository, pull):
        return {
            "repository": str(repository),
            "pr": int(pull),
            "check": self._check_pr_pull(repository, pull),
            "pull": self.pull(repository, pull),
        }

    def observe_reviews(self, repository, *pulls, issue=None, serial=False):
        """Expand review facts into submissions, comments, and thread evidence."""
        return self._run_check(
            self._observe_reviews_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_reviews_pull(self, repository, pull):
        return {
            "repository": str(repository),
            "pr": int(pull),
            "check": self._check_reviews_pull(repository, pull),
            "review_decision": self.review_decision(repository, pull),
            "reviews": self.reviews(repository, pull),
            "threads": self.review_threads(repository, pull),
            "comments": self.review_comments(repository, pull),
        }

    def observe_freshness(self, repository, *pulls, issue=None, serial=False):
        """Expand freshness facts into full PR and compare evidence."""
        return self._run_check(
            self._observe_freshness_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_freshness_pull(self, repository, pull):
        check = self._check_freshness_pull(repository, pull)
        evidence = None
        if check.get("base_sha") and check.get("head_sha"):
            evidence = self.compare(repository, check["base_sha"], check["head_sha"])
        return {
            "repository": str(repository),
            "pr": int(pull),
            "check": check,
            "pull": self.pull(repository, pull),
            "compare": evidence,
        }

    def observe_merge(self, repository, *pulls, issue=None, serial=False):
        """Expand merge facts into mergeability, reviews, and head checks."""
        return self._run_check(
            self._observe_merge_pull,
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_merge_pull(self, repository, pull):
        check = self._check_merge_pull(repository, pull)
        pr = self.pull(repository, pull)
        head = (pr.get("head") or {}).get("sha")
        return {
            "repository": str(repository),
            "pr": int(pull),
            "check": check,
            "pull": pr,
            "review_decision": self.review_decision(repository, pull),
            "checks": self.checks(repository, head) if head else [],
        }

    def observe_ci(
        self,
        repository,
        *pulls,
        issue=None,
        run=None,
        job=None,
        logs="failed",
        serial=False,
    ):
        """Expand CI checks into run/job/log/artifact provider evidence.

        ``--run``/``--job`` is the direct diagnostic-target path used by status.
        Otherwise one or more PR targets are resolved exactly like ``check ci``.
        """
        mode = self._log_mode(logs)
        if run is not None or job is not None:
            if pulls or issue is not None:
                raise ValueError("PR targets/--issue and --run/--job are mutually exclusive")
            return self._observe_ci_target(repository, run=run, job=job, logs=mode)
        return self._run_check(
            lambda repo, pull: self._observe_ci_pull(repo, pull, logs=mode),
            repository,
            pulls,
            issue=issue,
            serial=serial,
        )

    def _observe_ci_target(self, repository, *, run=None, job=None, logs="failed"):
        job_data = self.job(repository, int(job)) if job is not None else None
        if run is None and job_data is not None:
            run = job_data.get("run_id")
        if run is None:
            raise ValueError("direct CI observation requires --run or --job")

        run_data = self.run(repository, int(run))
        jobs = self.jobs(repository, int(run))
        if job_data is not None:
            selected = [item for item in jobs if item.get("id") == int(job)]
            if not selected:
                selected = [job_data]
            jobs = selected

        evidence_jobs = []
        for item in jobs:
            detail = self.job(repository, item["id"]) if item.get("id") else item
            observed = {"job": detail}
            if item.get("id") and _want_log(detail, logs):
                observed["log"] = _log_text(self.job_logs(repository, item["id"]))
            evidence_jobs.append(observed)

        head = run_data.get("head_sha")
        check_runs = []
        if head:
            for item in self.checks(repository, head):
                check_runs.append(
                    {
                        "check": item,
                        "annotations": self.check_annotations(repository, item["id"])
                        if item.get("id")
                        else [],
                    }
                )

        artifacts = self.artifacts(repository, int(run))
        canonical = []
        for artifact in artifacts:
            if artifact.get("name") != "gway-ci-result" or not artifact.get("id"):
                continue
            entry = {"artifact": artifact}
            try:
                entry["result"] = self.artifact_json(repository, artifact["id"])
            except (
                ValueError,
                TypeError,
                json.JSONDecodeError,
                zipfile.BadZipFile,
            ) as exc:
                entry["error"] = str(exc)
            canonical.append(entry)

        return {
            "repository": str(repository),
            "run": int(run),
            "job": int(job) if job is not None else None,
            "workflow": run_data,
            "jobs": evidence_jobs,
            "check_runs": check_runs,
            "artifacts": artifacts,
            "canonical_results": canonical,
        }

    def _observe_ci_pull(self, repository, pull, *, logs="failed"):
        check = self._check_ci_pull(repository, pull)
        workflows = []
        for summary in check.get("workflows", ()):
            run_id = summary.get("id")
            if run_id is None:
                continue
            evidence = self._observe_ci_target(repository, run=run_id, logs=logs)
            evidence["summary"] = summary
            workflows.append(evidence)
        return {
            "repository": str(repository),
            "pr": int(pull),
            "check": check,
            "workflows": workflows,
        }
